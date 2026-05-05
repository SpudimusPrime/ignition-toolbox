"""
Parameter resolution system

Handles resolving parameter references like:
- {{ credential.gateway_admin }} -> actual password from vault
- {{ variable.module_name }} -> value from runtime variables
- {{ parameter.gateway_url }} -> value from playbook parameters
"""

import re
from pathlib import Path
from typing import Any

from ignition_toolkit.credentials import CredentialVault
from ignition_toolkit.playbook.exceptions import ParameterResolutionError


class ParameterResolver:
    """
    Resolve parameter references in playbook values

    Supports three types of references:
    1. {{ credential.name }} - Load from credential vault
    2. {{ variable.name }} - Load from runtime variables
    3. {{ parameter.name }} - Load from playbook parameters

    Example:
        resolver = ParameterResolver(
            credential_vault=vault,
            parameters={"gateway_url": "http://localhost:8088"},
            variables={"module_name": "Perspective"}
        )
        resolved = resolver.resolve("{{ credential.gateway_admin }}")
    """

    # Pattern to match {{ type.name.attr }} or {{ type.name }} or {{ name }}
    PATTERN = re.compile(r"\{\{\s*(\w+)(?:\.(\w+))?(?:\.(\w+))?\s*\}\}")

    def __init__(
        self,
        credential_vault: CredentialVault | None = None,
        parameters: dict[str, Any] | None = None,
        variables: dict[str, Any] | None = None,
        step_results: dict[str, dict[str, Any]] | None = None,
    ):
        """
        Initialize parameter resolver

        Args:
            credential_vault: Credential vault for loading credentials
            parameters: Playbook parameters
            variables: Runtime variables
            step_results: Dictionary mapping step_id to step output (for {{ step.step_id.key }} references)
        """
        self.credential_vault = credential_vault
        self.parameters = parameters if parameters is not None else {}
        self.variables = variables if variables is not None else {}
        self.step_results = step_results if step_results is not None else {}

    def resolve(self, value: Any) -> Any:
        """
        Resolve parameter references in value

        Args:
            value: Value to resolve (string, dict, list, or primitive)

        Returns:
            Resolved value with references replaced

        Raises:
            ParameterResolutionError: If reference cannot be resolved
        """
        if isinstance(value, str):
            return self._resolve_string(value)
        elif isinstance(value, dict):
            return {k: self.resolve(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [self.resolve(item) for item in value]
        else:
            # Primitive value (int, float, bool, None)
            return value

    def _resolve_string(self, value: str) -> Any:
        """
        Resolve references in string value

        Args:
            value: String value (may contain {{ ... }} references)

        Returns:
            Resolved value (string or other type if fully replaced)

        Raises:
            ParameterResolutionError: If reference cannot be resolved
        """
        # Find all matches
        matches = list(self.PATTERN.finditer(value))

        if not matches:
            # No references, return as-is
            return value

        # If the entire string is a single reference, return the actual value
        # (allows non-string values like credentials to be returned)
        # However, for parameters and variables, convert to string to maintain template semantics
        if len(matches) == 1 and matches[0].group(0) == value:
            ref_type = matches[0].group(1)
            ref_name = matches[0].group(2)
            ref_attr = matches[0].group(3)

            # If ref_name is None, it means bare parameter name like {{ gateway_url }}
            if ref_name is None:
                ref_name = ref_type
                ref_type = "parameter"

            resolved = self._resolve_reference(ref_type, ref_name)

            # If attribute access is specified, get the attribute
            if ref_attr:
                resolved = self._get_attribute(resolved, ref_attr, ref_type, ref_name)

            # For credentials without attribute access, return as-is (may be Credential object)
            # Also check if resolved value is a Credential object (from credential-type parameters)
            if ref_type == "credential" and not ref_attr:
                return resolved

            # Check if the resolved value is a Credential object (even if ref_type is "parameter")
            # This happens when credential-type parameters are preprocessed by the engine
            from ignition_toolkit.credentials import Credential
            if isinstance(resolved, Credential) and not ref_attr:
                return resolved

            # For parameters/variables in template context, convert to string
            return str(resolved)

        # Multiple references or mixed content - build string
        result = value
        for match in reversed(matches):  # Reverse to preserve positions
            ref_type = match.group(1)
            ref_name = match.group(2)
            ref_attr = match.group(3)

            # If ref_name is None, it means bare parameter name like {{ gateway_url }}
            if ref_name is None:
                ref_name = ref_type
                ref_type = "parameter"

            resolved = self._resolve_reference(ref_type, ref_name)

            # If attribute access is specified, get the attribute
            if ref_attr:
                resolved = self._get_attribute(resolved, ref_attr, ref_type, ref_name)

            replacement = str(resolved)
            result = result[: match.start()] + replacement + result[match.end() :]

        return result

    def _resolve_reference(self, ref_type: str, ref_name: str) -> Any:
        """
        Resolve individual reference

        Args:
            ref_type: Reference type (credential, variable, parameter, step)
            ref_name: Reference name

        Returns:
            Resolved value

        Raises:
            ParameterResolutionError: If reference cannot be resolved
        """
        if ref_type == "credential":
            return self._resolve_credential(ref_name)
        elif ref_type == "variable":
            return self._resolve_variable(ref_name)
        elif ref_type == "parameter":
            return self._resolve_parameter(ref_name)
        elif ref_type == "step":
            return self._resolve_step(ref_name)
        else:
            raise ParameterResolutionError(
                f"Unknown reference type '{ref_type}' (valid: credential, variable, parameter, step)"
            )

    def _resolve_credential(self, name: str) -> Any:
        """
        Resolve credential reference

        Args:
            name: Credential name

        Returns:
            Credential object

        Raises:
            ParameterResolutionError: If credential not found
        """
        if self.credential_vault is None:
            raise ParameterResolutionError(
                f"Cannot resolve credential '{name}': no credential vault configured"
            )

        try:
            credential = self.credential_vault.get_credential(name)
            if credential is None:
                raise ParameterResolutionError(f"Credential '{name}' not found in vault")
            return credential
        except Exception as e:
            raise ParameterResolutionError(f"Error loading credential '{name}': {e}")

    def _resolve_variable(self, name: str) -> Any:
        """
        Resolve variable reference

        Args:
            name: Variable name

        Returns:
            Variable value

        Raises:
            ParameterResolutionError: If variable not found
        """
        if name not in self.variables:
            raise ParameterResolutionError(f"Variable '{name}' not found in runtime variables")
        return self.variables[name]

    def _resolve_parameter(self, name: str) -> Any:
        """
        Resolve parameter reference

        Args:
            name: Parameter name

        Returns:
            Parameter value

        Raises:
            ParameterResolutionError: If parameter not found
        """
        if name not in self.parameters:
            raise ParameterResolutionError(f"Parameter '{name}' not found in playbook parameters")
        return self.parameters[name]

    def _resolve_step(self, name: str) -> Any:
        """
        Resolve step output reference

        Args:
            name: Step ID

        Returns:
            Step output dictionary

        Raises:
            ParameterResolutionError: If step not found or has no output
        """
        if name not in self.step_results:
            raise ParameterResolutionError(
                f"Step '{name}' not found or has not been executed yet. "
                f"Step references can only access outputs from previously completed steps."
            )
        output = self.step_results[name]
        if output is None or (isinstance(output, dict) and not output):
            raise ParameterResolutionError(
                f"Step '{name}' has no output data. "
                f"Only steps that return data (like utility.python) can be referenced."
            )
        return output

    def _get_attribute(self, obj: Any, attr_name: str, ref_type: str, ref_name: str) -> Any:
        """
        Get attribute from resolved object

        Args:
            obj: Object to get attribute from
            attr_name: Attribute name
            ref_type: Reference type (for error messages)
            ref_name: Reference name (for error messages)

        Returns:
            Attribute value

        Raises:
            ParameterResolutionError: If attribute not found
        """
        try:
            # Handle dictionaries (like step results)
            if isinstance(obj, dict):
                if attr_name in obj:
                    value = obj[attr_name]
                    # Handle None values
                    if value is None:
                        raise ParameterResolutionError(
                            f"Attribute '{attr_name}' of {ref_type} '{ref_name}' is None"
                        )
                    return value
                else:
                    raise ParameterResolutionError(
                        f"Attribute '{attr_name}' not found on {ref_type} '{ref_name}'"
                    )
            # Handle objects with attributes
            elif hasattr(obj, attr_name):
                value = getattr(obj, attr_name)
                # Handle None values
                if value is None:
                    raise ParameterResolutionError(
                        f"Attribute '{attr_name}' of {ref_type} '{ref_name}' is None"
                    )
                return value
            else:
                raise ParameterResolutionError(
                    f"Attribute '{attr_name}' not found on {ref_type} '{ref_name}'"
                )
        except ParameterResolutionError:
            raise
        except Exception as e:
            raise ParameterResolutionError(
                f"Error accessing attribute '{attr_name}' on {ref_type} '{ref_name}': {e}"
            )

    def resolve_skip_if(self, skip_if: str) -> bool:
        """
        Evaluate a skip_if expression.

        Returns True (skip the step) when the expression resolves to a truthy value.
        Missing variables resolve to falsy so steps always run when the variable hasn't
        been set yet — allowing the same playbook to be run standalone or chained.

        Supported forms (after template substitution):
          Truthiness:  "{{ variable.session_logged_in }}"
          Equality:    "{{ variable.navigation }} = materials"
          Inequality:  "{{ variable.navigation }} != materials"
        """
        try:
            resolved = self._resolve_string(skip_if)
        except ParameterResolutionError:
            return False  # Variable not defined → don't skip

        if isinstance(resolved, bool):
            return resolved

        if not isinstance(resolved, str):
            return bool(resolved)

        s = resolved.strip()

        # Inequality must be checked before equality (!=  vs =)
        if " != " in s:
            left, right = s.split(" != ", 1)
            return left.strip() != right.strip()

        if " = " in s:
            left, right = s.split(" = ", 1)
            return left.strip() == right.strip()

        return s.lower() not in ("", "false", "0", "null", "none")

    def resolve_file_path(self, path: str, base_path: Path | None = None) -> Path:
        """
        Resolve file path (handle relative paths)

        Args:
            path: File path (may be relative)
            base_path: Base path for resolving relative paths

        Returns:
            Absolute Path object

        Raises:
            ParameterResolutionError: If file not found
        """
        # Resolve any parameter references first
        resolved_path = self.resolve(path)

        if not isinstance(resolved_path, (str, Path)):
            raise ParameterResolutionError(
                f"File path must be string or Path, got {type(resolved_path)}"
            )

        path_obj = Path(resolved_path)

        # Make absolute
        if not path_obj.is_absolute():
            if base_path:
                path_obj = base_path / path_obj
            else:
                path_obj = path_obj.resolve()

        # Validate exists
        if not path_obj.exists():
            raise ParameterResolutionError(f"File not found: {path_obj}")

        return path_obj
