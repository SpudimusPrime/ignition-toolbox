"""
Playbook loader - YAML parsing and validation

Handles loading playbook definitions from YAML files with validation.
"""

from pathlib import Path
from typing import Any

import yaml

from ignition_toolkit.playbook.exceptions import (
    PlaybookLoadError,
    PlaybookValidationError,
    YAMLParseError,
)
from ignition_toolkit.playbook.models import (
    OnFailureAction,
    ParameterType,
    Playbook,
    PlaybookParameter,
    PlaybookStep,
    StepType,
)


class PlaybookLoader:
    """
    Load and validate YAML playbooks

    Example:
        loader = PlaybookLoader()
        playbook = loader.load_from_file("module_upgrade.yaml")
    """

    @staticmethod
    def load_from_file(file_path: Path) -> Playbook:
        """
        Load playbook from YAML file

        Args:
            file_path: Path to YAML file

        Returns:
            Parsed and validated playbook

        Raises:
            PlaybookLoadError: If file cannot be loaded
            PlaybookValidationError: If playbook structure is invalid
        """
        if not file_path.exists():
            raise PlaybookLoadError(
                "File not found",
                file_path=str(file_path),
                recovery_hint="Check that the playbook file exists and the path is correct",
            )

        try:
            with open(file_path, encoding='utf-8') as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            # Extract line number from YAML error
            line_number = None
            column = None
            if hasattr(e, 'problem_mark') and e.problem_mark:
                line_number = e.problem_mark.line + 1  # Convert to 1-indexed
                column = e.problem_mark.column + 1

            raise YAMLParseError(
                message=str(e.problem) if hasattr(e, 'problem') else str(e),
                file_path=str(file_path),
                line_number=line_number,
                column=column,
            )
        except OSError as e:
            raise PlaybookLoadError(
                f"Error reading file: {e}",
                file_path=str(file_path),
                recovery_hint="Check file permissions and that the file is not locked",
            )

        return PlaybookLoader._parse_playbook(data, file_path)

    @staticmethod
    def load_from_string(yaml_content: str) -> Playbook:
        """
        Load playbook from YAML string

        Args:
            yaml_content: YAML content as string

        Returns:
            Parsed and validated playbook

        Raises:
            PlaybookLoadError: If YAML cannot be parsed
            PlaybookValidationError: If playbook structure is invalid
        """
        try:
            data = yaml.safe_load(yaml_content)
        except yaml.YAMLError as e:
            # Extract line number from YAML error
            line_number = None
            column = None
            if hasattr(e, 'problem_mark') and e.problem_mark:
                line_number = e.problem_mark.line + 1  # Convert to 1-indexed
                column = e.problem_mark.column + 1

            raise YAMLParseError(
                message=str(e.problem) if hasattr(e, 'problem') else str(e),
                line_number=line_number,
                column=column,
            )

        return PlaybookLoader._parse_playbook(data, None)

    @staticmethod
    def save_to_file(playbook: Playbook, file_path: Path) -> None:
        """
        Save playbook to YAML file

        Args:
            playbook: Playbook to save
            file_path: Output file path

        Raises:
            PlaybookLoadError: If file cannot be written
        """
        data = PlaybookLoader._serialize_playbook(playbook)

        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, "w", encoding='utf-8') as f:
                yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)
        except Exception as e:
            raise PlaybookLoadError(f"Error writing file: {e}")

    @staticmethod
    def _parse_playbook(data: dict[str, Any], source_path: Path = None) -> Playbook:
        """
        Parse playbook data structure

        Args:
            data: Parsed YAML data
            source_path: Source file path (for error messages)

        Returns:
            Playbook object

        Raises:
            PlaybookValidationError: If structure is invalid
        """
        if not isinstance(data, dict):
            raise PlaybookValidationError("Playbook must be a dictionary")

        # Required fields
        if "name" not in data:
            raise PlaybookValidationError("Playbook must have 'name' field")
        if "version" not in data:
            raise PlaybookValidationError("Playbook must have 'version' field")
        if "steps" not in data:
            raise PlaybookValidationError("Playbook must have 'steps' field")

        # Parse parameters
        parameters = []
        if "parameters" in data:
            if not isinstance(data["parameters"], list):
                raise PlaybookValidationError("'parameters' must be a list")
            for param_data in data["parameters"]:
                parameters.append(PlaybookLoader._parse_parameter(param_data))

        # Parse steps
        steps = []
        if not isinstance(data["steps"], list):
            raise PlaybookValidationError("'steps' must be a list")
        if len(data["steps"]) == 0:
            raise PlaybookValidationError("Playbook must have at least one step")

        for step_data in data["steps"]:
            steps.append(PlaybookLoader._parse_step(step_data))

        # Validate unique step IDs
        step_ids = [step.id for step in steps]
        if len(step_ids) != len(set(step_ids)):
            raise PlaybookValidationError("Step IDs must be unique")

        # Build metadata dict - include domain, group, and verified if present at root level
        metadata = data.get("metadata", {})
        if "domain" in data:
            metadata["domain"] = data["domain"]
        if "group" in data:
            metadata["group"] = data["group"]
        if "verified" in data:
            metadata["verified"] = data["verified"]

        return Playbook(
            name=data["name"],
            version=data["version"],
            description=data.get("description", ""),
            parameters=parameters,
            steps=steps,
            metadata=metadata,
        )

    @staticmethod
    def _parse_parameter(data: dict[str, Any]) -> PlaybookParameter:
        """
        Parse parameter definition

        Args:
            data: Parameter data

        Returns:
            PlaybookParameter object

        Raises:
            PlaybookValidationError: If parameter is invalid
        """
        if not isinstance(data, dict):
            raise PlaybookValidationError("Parameter must be a dictionary")

        if "name" not in data:
            raise PlaybookValidationError("Parameter must have 'name' field")
        if "type" not in data:
            raise PlaybookValidationError("Parameter must have 'type' field")

        # Parse type
        try:
            param_type = ParameterType(data["type"])
        except ValueError:
            valid_types = [t.value for t in ParameterType]
            raise PlaybookValidationError(
                f"Invalid parameter type '{data['type']}'. "
                f"Valid types: {', '.join(valid_types)}"
            )

        return PlaybookParameter(
            name=data["name"],
            type=param_type,
            required=data.get("required", True),
            default=data.get("default"),
            description=data.get("description", ""),
        )

    @staticmethod
    def _parse_step(data: dict[str, Any]) -> PlaybookStep:
        """
        Parse step definition

        Args:
            data: Step data

        Returns:
            PlaybookStep object

        Raises:
            PlaybookValidationError: If step is invalid
        """
        if not isinstance(data, dict):
            raise PlaybookValidationError("Step must be a dictionary")

        if "id" not in data:
            raise PlaybookValidationError("Step must have 'id' field")
        if "name" not in data:
            raise PlaybookValidationError("Step must have 'name' field")
        if "type" not in data:
            raise PlaybookValidationError("Step must have 'type' field")

        # Parse type
        try:
            step_type = StepType(data["type"])
        except ValueError:
            valid_types = [t.value for t in StepType]
            raise PlaybookValidationError(
                f"Invalid step type '{data['type']}'. " f"Valid types: {', '.join(valid_types)}"
            )

        # Parse on_failure
        on_failure = OnFailureAction.ABORT
        if "on_failure" in data:
            try:
                on_failure = OnFailureAction(data["on_failure"])
            except ValueError:
                valid_actions = [a.value for a in OnFailureAction]
                raise PlaybookValidationError(
                    f"Invalid on_failure action '{data['on_failure']}'. "
                    f"Valid actions: {', '.join(valid_actions)}"
                )

        return PlaybookStep(
            id=data["id"],
            name=data["name"],
            type=step_type,
            parameters=data.get("parameters", {}),
            on_failure=on_failure,
            timeout=data.get("timeout", 300),
            retry_count=data.get("retry_count", 0),
            retry_delay=data.get("retry_delay", 5),
            skip_if=data.get("skip_if") or None,
        )

    @staticmethod
    def _serialize_playbook(playbook: Playbook) -> dict[str, Any]:
        """
        Convert playbook to dictionary for YAML serialization

        Args:
            playbook: Playbook to serialize

        Returns:
            Dictionary representation
        """
        return {
            "name": playbook.name,
            "version": playbook.version,
            "description": playbook.description,
            "parameters": [
                {
                    "name": p.name,
                    "type": p.type.value,
                    "required": p.required,
                    "default": p.default,
                    "description": p.description,
                }
                for p in playbook.parameters
            ],
            "steps": [
                {
                    k: v for k, v in {
                        "id": s.id,
                        "name": s.name,
                        "type": s.type.value,
                        "parameters": s.parameters,
                        "on_failure": s.on_failure.value,
                        "timeout": s.timeout,
                        "retry_count": s.retry_count,
                        "retry_delay": s.retry_delay,
                        "skip_if": s.skip_if,
                    }.items() if v is not None
                }
                for s in playbook.steps
            ],
            "metadata": playbook.metadata,
        }
