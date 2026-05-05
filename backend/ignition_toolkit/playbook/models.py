"""
Playbook models and data structures

Defines the core data models for playbook definitions, parameters, and execution state.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class ParameterType(str, Enum):
    """Parameter type for playbook inputs"""

    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    FILE = "file"
    CREDENTIAL = "credential"
    LIST = "list"
    DICT = "dict"


class StepType(str, Enum):
    """Step type for playbook actions"""

    # Gateway operations
    GATEWAY_LOGIN = "gateway.login"
    GATEWAY_LOGOUT = "gateway.logout"
    GATEWAY_PING = "gateway.ping"
    GATEWAY_GET_INFO = "gateway.get_info"
    GATEWAY_GET_HEALTH = "gateway.get_health"
    GATEWAY_LIST_MODULES = "gateway.list_modules"
    GATEWAY_UPLOAD_MODULE = "gateway.upload_module"
    GATEWAY_WAIT_MODULE = "gateway.wait_for_module_installation"
    GATEWAY_LIST_PROJECTS = "gateway.list_projects"
    GATEWAY_GET_PROJECT = "gateway.get_project"
    GATEWAY_RESTART = "gateway.restart"
    GATEWAY_WAIT_READY = "gateway.wait_for_ready"

    # Browser operations (future)
    BROWSER_NAVIGATE = "browser.navigate"
    BROWSER_CLICK = "browser.click"
    BROWSER_FILL = "browser.fill"
    BROWSER_KEYBOARD = "browser.keyboard"
    BROWSER_FILE_UPLOAD = "browser.file_upload"
    BROWSER_SCREENSHOT = "browser.screenshot"
    BROWSER_WAIT = "browser.wait"
    BROWSER_VERIFY = "browser.verify"
    BROWSER_VERIFY_TEXT = "browser.verify_text"
    BROWSER_VERIFY_ATTRIBUTE = "browser.verify_attribute"
    BROWSER_VERIFY_STATE = "browser.verify_state"
    BROWSER_GET_TEXT = "browser.get_text"

    # Designer operations (desktop application automation)
    DESIGNER_LAUNCH = "designer.launch"
    DESIGNER_LAUNCH_SHORTCUT = "designer.launch_shortcut"
    DESIGNER_LOGIN = "designer.login"
    DESIGNER_OPEN_PROJECT = "designer.open_project"
    DESIGNER_CLOSE = "designer.close"
    DESIGNER_SCREENSHOT = "designer.screenshot"
    DESIGNER_WAIT = "designer.wait"

    # Playbook operations (composable playbooks)
    PLAYBOOK_RUN = "playbook.run"

    # Utility operations
    SLEEP = "utility.sleep"
    LOG = "utility.log"
    SET_VARIABLE = "utility.set_variable"
    PYTHON = "utility.python"

    # Perspective FAT testing operations
    PERSPECTIVE_DISCOVER_PAGE = "perspective.discover_page"
    PERSPECTIVE_EXTRACT_METADATA = "perspective.extract_component_metadata"
    PERSPECTIVE_EXECUTE_TEST_MANIFEST = "perspective.execute_test_manifest"
    PERSPECTIVE_VERIFY_NAVIGATION = "perspective.verify_navigation"
    PERSPECTIVE_VERIFY_DOCK = "perspective.verify_dock_opened"
    PERSPECTIVE_VERIFY_WITH_AI = "perspective.verify_with_ai"

    # FAT reporting operations
    FAT_GENERATE_REPORT = "fat.generate_report"
    FAT_EXPORT_REPORT = "fat.export_report"

    @property
    def domain(self) -> str:
        """Extract the domain prefix from the step type value (e.g. 'gateway' from 'gateway.login')."""
        return self.value.split(".")[0]


class ExecutionStatus(str, Enum):
    """Status of playbook execution"""

    PENDING = "pending"
    STARTED = "started"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StepStatus(str, Enum):
    """Status of individual step execution"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class OnFailureAction(str, Enum):
    """Action to take when a step fails"""

    ABORT = "abort"
    CONTINUE = "continue"
    ROLLBACK = "rollback"


@dataclass
class PlaybookParameter:
    """
    Parameter definition for playbook

    Attributes:
        name: Parameter name
        type: Parameter type (string, int, credential, etc.)
        required: Whether parameter is required
        default: Default value if not provided
        description: Human-readable description
    """

    name: str
    type: ParameterType
    required: bool = True
    default: Any | None = None
    description: str = ""

    def validate(self, value: Any) -> bool:
        """
        Validate parameter value against type

        Args:
            value: Value to validate

        Returns:
            True if valid

        Raises:
            ValueError: If value is invalid
        """
        if value is None:
            if self.required and self.default is None:
                raise ValueError(f"Required parameter '{self.name}' is missing")
            return True

        # Type validation
        if self.type == ParameterType.STRING:
            if not isinstance(value, str):
                raise ValueError(f"Parameter '{self.name}' must be a string")
        elif self.type == ParameterType.INTEGER:
            if not isinstance(value, int):
                raise ValueError(f"Parameter '{self.name}' must be an integer")
        elif self.type == ParameterType.FLOAT:
            if not isinstance(value, (int, float)):
                raise ValueError(f"Parameter '{self.name}' must be a number")
        elif self.type == ParameterType.BOOLEAN:
            if not isinstance(value, bool):
                raise ValueError(f"Parameter '{self.name}' must be a boolean")
        elif self.type == ParameterType.LIST:
            if not isinstance(value, list):
                raise ValueError(f"Parameter '{self.name}' must be a list")
        elif self.type == ParameterType.DICT:
            if not isinstance(value, dict):
                raise ValueError(f"Parameter '{self.name}' must be a dict")

        return True


@dataclass
class PlaybookStep:
    """
    Individual step in a playbook

    Attributes:
        id: Unique step identifier
        name: Human-readable step name
        type: Step type (gateway.login, browser.click, etc.)
        parameters: Parameters for step execution
        on_failure: Action on failure (abort, continue, rollback)
        timeout: Step timeout in seconds
        retry_count: Number of retries on failure
        retry_delay: Delay between retries in seconds
        skip_if: Template expression; step is skipped when it resolves to a truthy value.
                 Missing variables resolve to falsy so the step always runs when unset.
                 Example: "{{ variable.session_logged_in }}"
    """

    id: str
    name: str
    type: StepType
    parameters: dict[str, Any] = field(default_factory=dict)
    on_failure: OnFailureAction = OnFailureAction.ABORT
    timeout: int = 300
    retry_count: int = 0
    retry_delay: int = 5
    skip_if: str | None = None


@dataclass
class Playbook:
    """
    Playbook definition

    Attributes:
        name: Playbook name
        version: Playbook version
        description: Human-readable description
        parameters: List of parameter definitions
        steps: List of execution steps
        metadata: Additional metadata
    """

    name: str
    version: str
    description: str = ""
    parameters: list[PlaybookParameter] = field(default_factory=list)
    steps: list[PlaybookStep] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def get_parameter(self, name: str) -> PlaybookParameter | None:
        """
        Get parameter definition by name

        Args:
            name: Parameter name

        Returns:
            Parameter definition or None
        """
        for param in self.parameters:
            if param.name == name:
                return param
        return None

    def get_step(self, step_id: str) -> PlaybookStep | None:
        """
        Get step by ID

        Args:
            step_id: Step identifier

        Returns:
            Step or None
        """
        for step in self.steps:
            if step.id == step_id:
                return step
        return None


@dataclass
class StepResult:
    """
    Result of step execution

    Attributes:
        step_id: Step identifier
        step_name: Step name
        status: Execution status
        started_at: Start timestamp
        completed_at: Completion timestamp
        output: Step output data
        error: Error message if failed
        retry_count: Number of retries attempted
    """

    step_id: str
    step_name: str
    status: StepStatus
    started_at: datetime
    completed_at: datetime | None = None
    output: dict[str, Any] | None = None
    error: str | None = None
    retry_count: int = 0
    nested_steps: list[dict[str, Any]] | None = None


@dataclass
class ExecutionState:
    """
    Current state of playbook execution

    Attributes:
        execution_id: Unique execution identifier
        playbook_name: Name of playbook being executed
        status: Current execution status
        started_at: Execution start timestamp
        completed_at: Execution completion timestamp
        current_step_index: Index of current step
        total_steps: Total number of steps in playbook
        debug_mode: Whether debug mode is enabled
        step_results: Results of completed steps
        variables: Runtime variables
        error: Error message if failed
        domain: Playbook domain (gateway, designer, perspective)
    """

    execution_id: str
    playbook_name: str
    status: ExecutionStatus
    started_at: datetime
    completed_at: datetime | None = None
    current_step_index: int = 0
    total_steps: int = 0
    debug_mode: bool = False
    step_results: list[StepResult] = field(default_factory=list)
    variables: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    domain: str | None = None  # Playbook domain (gateway, designer, perspective)

    def get_step_result(self, step_id: str) -> StepResult | None:
        """
        Get result for specific step

        Args:
            step_id: Step identifier

        Returns:
            Step result or None
        """
        for result in self.step_results:
            if result.step_id == step_id:
                return result
        return None

    def add_step_result(self, result: StepResult) -> None:
        """
        Add or update step result in execution state

        Args:
            result: Step result to add or update
        """
        # Check if step already exists (from pre-population)
        for i, existing_result in enumerate(self.step_results):
            if existing_result.step_id == result.step_id:
                # Update in place
                self.step_results[i] = result
                return
        # If not found, append (fallback for backward compatibility)
        self.step_results.append(result)
