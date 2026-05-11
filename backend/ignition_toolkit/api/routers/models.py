"""
Shared Pydantic models for API routers

Centralized model definitions to avoid duplication across routers.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, field_validator

from ignition_toolkit.core.validation_limits import ValidationLimits

# ============================================================================
# Playbook Models
# ============================================================================


class ParameterInfo(BaseModel):
    """Parameter definition for frontend"""

    name: str
    type: str
    required: bool
    default: str | None = None
    description: str = ""


class StepInfo(BaseModel):
    """Step definition for frontend"""

    id: str
    name: str
    type: str
    timeout: int
    retry_count: int


class PlaybookInfo(BaseModel):
    """Playbook metadata"""

    name: str
    path: str
    version: str
    description: str
    parameter_count: int
    step_count: int
    parameters: list[ParameterInfo] = []
    steps: list[StepInfo] = []
    # Metadata fields
    domain: str | None = None  # Playbook domain (gateway, designer, perspective)
    group: str | None = None  # Playbook group for UI organization (e.g., "Gateway (Base Playbooks)")
    revision: int = 0
    verified: bool = False
    enabled: bool = True
    last_modified: str | None = None
    verified_at: str | None = None
    last_committed_at: str | None = None  # When last pushed to private repo
    load_error: str | None = None  # Set when the YAML file failed to parse
    # PORTABILITY v4: Origin tracking fields
    origin: str = "unknown"  # built-in, user-created, duplicated, unknown
    duplicated_from: str | None = None  # Source playbook path if duplicated
    created_at: str | None = None  # When playbook was created/added
    relevant_timeouts: list[str] = []  # Timeout categories applicable to this playbook


# ============================================================================
# Execution Models
# ============================================================================


class ExecutionRequest(BaseModel):
    """Request to execute a playbook"""

    playbook_path: str
    parameters: dict[str, Any]  # Allow any type (bool, str, int, etc.)
    gateway_url: str | None = None
    credential_name: str | None = None  # Name of saved credential to use
    debug_mode: bool | None = False  # Enable debug mode for this execution
    timeout_overrides: dict[str, int] | None = None  # Per-playbook timeout overrides

    @field_validator("parameters")
    @classmethod
    def validate_parameters(cls, v: dict[str, Any]) -> dict[str, Any]:
        """Validate parameters to prevent injection attacks and DoS"""
        # Limit number of parameters
        if len(v) > ValidationLimits.PARAMETER_COUNT_MAX:
            raise ValueError(f"Too many parameters (max {ValidationLimits.PARAMETER_COUNT_MAX})")

        # Limit value length to prevent DoS
        for key, value in v.items():
            if len(key) > ValidationLimits.PARAMETER_NAME_MAX:
                raise ValueError(f"Parameter name too long (max {ValidationLimits.PARAMETER_NAME_MAX} chars)")

            # Only validate string values for length and dangerous characters
            if isinstance(value, str):
                if len(value) > ValidationLimits.PARAMETER_VALUE_MAX:
                    raise ValueError(f'Parameter "{key}" value too long (max {ValidationLimits.PARAMETER_VALUE_MAX} chars)')

                # Check for potentially dangerous characters
                import logging

                logger = logging.getLogger(__name__)
                dangerous_chars = [";", "--", "/*", "*/", "<?", "?>"]
                for char in dangerous_chars:
                    if char in value:
                        logger.warning(f'Potentially dangerous characters in parameter "{key}": {char}')

        return v

    @field_validator("gateway_url")
    @classmethod
    def validate_gateway_url(cls, v: str | None) -> str | None:
        """Validate gateway URL format"""
        if v is not None:
            if not v.startswith(("http://", "https://")):
                raise ValueError("Gateway URL must start with http:// or https://")
            if len(v) > ValidationLimits.GATEWAY_URL_MAX:
                raise ValueError(f"Gateway URL too long (max {ValidationLimits.GATEWAY_URL_MAX} chars)")
        return v


class ExecutionResponse(BaseModel):
    """Response with execution ID"""

    execution_id: str
    playbook_name: str
    status: str
    message: str


class StepResultResponse(BaseModel):
    """Step execution result"""

    step_id: str
    step_name: str
    status: str
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    output: dict[str, Any] | None = None
    nested_steps: list[dict[str, Any]] | None = None


class ExecutionStatusResponse(BaseModel):
    """Current execution status"""

    execution_id: str
    playbook_name: str
    status: str
    started_at: datetime
    completed_at: datetime | None
    current_step_index: int | None
    total_steps: int
    error: str | None
    debug_mode: bool = False
    step_results: list[StepResultResponse] | None = None
    domain: str | None = None  # Playbook domain (gateway, designer, perspective)
