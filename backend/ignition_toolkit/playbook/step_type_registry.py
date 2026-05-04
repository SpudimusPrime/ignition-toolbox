"""
Unified step type registry - single source of truth for step type metadata.

Every step type is defined here with its domain, description, parameters,
and timeout category. This eliminates duplication between:
  - api/routers/step_types.py (STEP_TYPE_METADATA descriptions and parameters)
  - api/routers/playbook_crud.py (_compute_relevant_timeouts logic)

To add a new step type:
  1. Add a new StepType enum member in models.py
  2. Add a new StepTypeDefinition entry in STEP_REGISTRY below
  3. Create the handler class in the appropriate executor file
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from pydantic import BaseModel

from ignition_toolkit.core.timeouts import TimeoutDefaults, TimeoutKeys
from ignition_toolkit.playbook.models import StepType

logger = logging.getLogger(__name__)


class StepParameter(BaseModel):
    """Parameter definition for a step type.

    This Pydantic model is the single authoritative definition used by both
    the registry and the step-types API endpoint. Previously duplicated in
    api/routers/step_types.py.
    """

    name: str
    type: str  # string, integer, float, boolean, credential, file, list, dict, selector
    required: bool = True
    default: str | int | float | bool | None = None
    description: str = ""
    options: list[str] | None = None  # For enum-like parameters


@dataclass
class StepTypeDefinition:
    """Complete definition of a step type including metadata and timeout info."""

    step_type: StepType
    """The enum value identifying this step type."""

    description: str
    """Human-readable description shown in the UI."""

    parameters: list[StepParameter] = field(default_factory=list)
    """Parameter definitions for the step editor."""

    timeout_category: str | None = None
    """
    Which timeout override category applies to this step type.
    Maps to a TimeoutKeys constant. Used by _compute_relevant_timeouts()
    to tell the frontend which timeout sliders are relevant for a playbook.
    None means no configurable timeout applies.
    """

    @property
    def domain(self) -> str:
        """The domain prefix extracted from the step type value."""
        return self.step_type.domain

    @property
    def type_value(self) -> str:
        """The string value of the step type (e.g. 'gateway.login')."""
        return self.step_type.value


# =============================================================================
# Registry — one entry per StepType enum member
# =============================================================================

STEP_REGISTRY: list[StepTypeDefinition] = [

    # ── Gateway ───────────────────────────────────────────────────────────────

    StepTypeDefinition(
        step_type=StepType.GATEWAY_LOGIN,
        description="Login to Ignition Gateway with username and password",
        parameters=[
            StepParameter(
                name="credential",
                type="credential",
                required=True,
                description="Credential containing gateway login information",
            ),
        ],
        timeout_category=None,
    ),
    StepTypeDefinition(
        step_type=StepType.GATEWAY_LOGOUT,
        description="Logout from Ignition Gateway",
        parameters=[],
        timeout_category=None,
    ),
    StepTypeDefinition(
        step_type=StepType.GATEWAY_PING,
        description="Ping the Gateway to verify connectivity",
        parameters=[],
        timeout_category=None,
    ),
    StepTypeDefinition(
        step_type=StepType.GATEWAY_GET_INFO,
        description="Get Gateway system information (version, edition, etc.)",
        parameters=[],
        timeout_category=None,
    ),
    StepTypeDefinition(
        step_type=StepType.GATEWAY_GET_HEALTH,
        description="Get Gateway health status",
        parameters=[],
        timeout_category=None,
    ),
    StepTypeDefinition(
        step_type=StepType.GATEWAY_LIST_MODULES,
        description="List all installed modules on the Gateway",
        parameters=[],
        timeout_category=None,
    ),
    StepTypeDefinition(
        step_type=StepType.GATEWAY_UPLOAD_MODULE,
        description="Upload and install a module (.modl file) to the Gateway",
        parameters=[
            StepParameter(
                name="file",
                type="file",
                required=True,
                description="Path to the .modl file to upload",
            ),
        ],
        timeout_category=TimeoutKeys.MODULE_INSTALL,
    ),
    StepTypeDefinition(
        step_type=StepType.GATEWAY_WAIT_MODULE,
        description="Wait for a module to finish installing",
        parameters=[
            StepParameter(
                name="module_name",
                type="string",
                required=True,
                description="Name of the module to wait for",
            ),
            StepParameter(
                name="timeout",
                type="integer",
                required=False,
                default=TimeoutDefaults.MODULE_INSTALL,
                description="Maximum time to wait in seconds",
            ),
        ],
        timeout_category=TimeoutKeys.MODULE_INSTALL,
    ),
    StepTypeDefinition(
        step_type=StepType.GATEWAY_LIST_PROJECTS,
        description="List all projects on the Gateway",
        parameters=[],
        timeout_category=None,
    ),
    StepTypeDefinition(
        step_type=StepType.GATEWAY_GET_PROJECT,
        description="Get details for a specific project",
        parameters=[
            StepParameter(
                name="project_name",
                type="string",
                required=True,
                description="Name of the project to retrieve",
            ),
        ],
        timeout_category=None,
    ),
    StepTypeDefinition(
        step_type=StepType.GATEWAY_RESTART,
        description="Restart the Ignition Gateway",
        parameters=[
            StepParameter(
                name="wait_for_ready",
                type="boolean",
                required=False,
                default=False,
                description="Wait for Gateway to be ready after restart",
            ),
            StepParameter(
                name="timeout",
                type="integer",
                required=False,
                default=TimeoutDefaults.GATEWAY_RESTART,
                description="Maximum time to wait in seconds",
            ),
        ],
        timeout_category=TimeoutKeys.GATEWAY_RESTART,
    ),
    StepTypeDefinition(
        step_type=StepType.GATEWAY_WAIT_READY,
        description="Wait for Gateway to be ready and accepting connections",
        parameters=[
            StepParameter(
                name="timeout",
                type="integer",
                required=False,
                default=TimeoutDefaults.GATEWAY_RESTART,
                description="Maximum time to wait in seconds",
            ),
        ],
        timeout_category=TimeoutKeys.GATEWAY_RESTART,
    ),

    # ── Browser ───────────────────────────────────────────────────────────────

    StepTypeDefinition(
        step_type=StepType.BROWSER_NAVIGATE,
        description="Navigate the browser to a URL",
        parameters=[
            StepParameter(
                name="url",
                type="string",
                required=True,
                description="URL to navigate to",
            ),
            StepParameter(
                name="wait_until",
                type="string",
                required=False,
                default="load",
                description="When to consider navigation complete",
                options=["load", "domcontentloaded", "networkidle"],
            ),
        ],
        timeout_category=TimeoutKeys.BROWSER_OPERATION,
    ),
    StepTypeDefinition(
        step_type=StepType.BROWSER_CLICK,
        description="Click on an element in the page",
        parameters=[
            StepParameter(
                name="selector",
                type="selector",
                required=True,
                description="CSS selector for the element to click",
            ),
            StepParameter(
                name="timeout",
                type="integer",
                required=False,
                default=TimeoutDefaults.BROWSER_ACTION,
                description="Maximum time to wait for element in milliseconds",
            ),
            StepParameter(
                name="force",
                type="boolean",
                required=False,
                default=False,
                description="Force click even if element is not visible",
            ),
        ],
        timeout_category=TimeoutKeys.BROWSER_OPERATION,
    ),
    StepTypeDefinition(
        step_type=StepType.BROWSER_FILL,
        description="Fill a form field with text",
        parameters=[
            StepParameter(
                name="selector",
                type="selector",
                required=True,
                description="CSS selector for the input element",
            ),
            StepParameter(
                name="value",
                type="string",
                required=True,
                description="Text value to fill",
            ),
            StepParameter(
                name="timeout",
                type="integer",
                required=False,
                default=TimeoutDefaults.BROWSER_ACTION,
                description="Maximum time to wait for element in milliseconds",
            ),
            StepParameter(
                name="fill_mode",
                type="string",
                required=False,
                default="fill",
                description=(
                    "Input strategy: 'fill' (default) sets value directly; "
                    "'type' types character-by-character to trigger React synthetic events. "
                    "Use 'type' for Perspective inputs that revert on blur."
                ),
            ),
        ],
        timeout_category=TimeoutKeys.BROWSER_OPERATION,
    ),
    StepTypeDefinition(
        step_type=StepType.BROWSER_KEYBOARD,
        description="Send keyboard input to the page",
        parameters=[
            StepParameter(
                name="key",
                type="string",
                required=True,
                description="Key or key combination to press (e.g., 'Enter', 'Control+A')",
            ),
        ],
        timeout_category=TimeoutKeys.BROWSER_OPERATION,
    ),
    StepTypeDefinition(
        step_type=StepType.BROWSER_FILE_UPLOAD,
        description="Upload a file through a file input element",
        parameters=[
            StepParameter(
                name="selector",
                type="selector",
                required=True,
                description="CSS selector for the file input element",
            ),
            StepParameter(
                name="file_path",
                type="file",
                required=True,
                description="Path to the file to upload",
            ),
            StepParameter(
                name="timeout",
                type="integer",
                required=False,
                default=TimeoutDefaults.BROWSER_ACTION,
                description="Maximum time to wait for element in milliseconds",
            ),
        ],
        timeout_category=TimeoutKeys.BROWSER_OPERATION,
    ),
    StepTypeDefinition(
        step_type=StepType.BROWSER_SCREENSHOT,
        description="Capture a screenshot of the current page",
        parameters=[
            StepParameter(
                name="name",
                type="string",
                required=False,
                description="Name for the screenshot file",
            ),
            StepParameter(
                name="full_page",
                type="boolean",
                required=False,
                default=False,
                description="Capture full scrollable page",
            ),
        ],
        timeout_category=TimeoutKeys.BROWSER_OPERATION,
    ),
    StepTypeDefinition(
        step_type=StepType.BROWSER_WAIT,
        description="Wait for an element to appear on the page",
        parameters=[
            StepParameter(
                name="selector",
                type="selector",
                required=True,
                description="CSS selector for the element to wait for",
            ),
            StepParameter(
                name="timeout",
                type="integer",
                required=False,
                default=TimeoutDefaults.BROWSER_ACTION,
                description="Maximum time to wait in milliseconds",
            ),
        ],
        timeout_category=TimeoutKeys.BROWSER_OPERATION,
    ),
    StepTypeDefinition(
        step_type=StepType.BROWSER_VERIFY,
        description="Verify that an element exists or does not exist",
        parameters=[
            StepParameter(
                name="selector",
                type="selector",
                required=True,
                description="CSS selector for the element to verify",
            ),
            StepParameter(
                name="exists",
                type="boolean",
                required=False,
                default=True,
                description="True to verify element exists, False to verify it doesn't",
            ),
            StepParameter(
                name="timeout",
                type="integer",
                required=False,
                default=TimeoutDefaults.BROWSER_VERIFY,
                description="Maximum time to wait in milliseconds",
            ),
        ],
        timeout_category=TimeoutKeys.BROWSER_OPERATION,
    ),
    StepTypeDefinition(
        step_type=StepType.BROWSER_VERIFY_TEXT,
        description="Verify text content of an element",
        parameters=[
            StepParameter(
                name="selector",
                type="selector",
                required=True,
                description="CSS selector for the element",
            ),
            StepParameter(
                name="text",
                type="string",
                required=True,
                description="Expected text content",
            ),
            StepParameter(
                name="match",
                type="string",
                required=False,
                default="exact",
                description="Match type: exact, contains, or regex",
                options=["exact", "contains", "regex"],
            ),
            StepParameter(
                name="timeout",
                type="integer",
                required=False,
                default=TimeoutDefaults.BROWSER_VERIFY,
                description="Maximum time to wait in milliseconds",
            ),
        ],
        timeout_category=TimeoutKeys.BROWSER_OPERATION,
    ),
    StepTypeDefinition(
        step_type=StepType.BROWSER_VERIFY_ATTRIBUTE,
        description="Verify an attribute value of an element",
        parameters=[
            StepParameter(
                name="selector",
                type="selector",
                required=True,
                description="CSS selector for the element",
            ),
            StepParameter(
                name="attribute",
                type="string",
                required=True,
                description="Name of the attribute to check",
            ),
            StepParameter(
                name="value",
                type="string",
                required=True,
                description="Expected attribute value",
            ),
            StepParameter(
                name="timeout",
                type="integer",
                required=False,
                default=TimeoutDefaults.BROWSER_VERIFY,
                description="Maximum time to wait in milliseconds",
            ),
        ],
        timeout_category=TimeoutKeys.BROWSER_OPERATION,
    ),
    StepTypeDefinition(
        step_type=StepType.BROWSER_VERIFY_STATE,
        description="Verify the state of an element (visible, hidden, enabled, disabled)",
        parameters=[
            StepParameter(
                name="selector",
                type="selector",
                required=True,
                description="CSS selector for the element",
            ),
            StepParameter(
                name="state",
                type="string",
                required=True,
                description="Expected state of the element",
                options=["visible", "hidden", "enabled", "disabled"],
            ),
            StepParameter(
                name="timeout",
                type="integer",
                required=False,
                default=TimeoutDefaults.BROWSER_VERIFY,
                description="Maximum time to wait in milliseconds",
            ),
        ],
        timeout_category=TimeoutKeys.BROWSER_OPERATION,
    ),
    StepTypeDefinition(
        step_type=StepType.BROWSER_GET_TEXT,
        description="Get the text content of an element",
        parameters=[
            StepParameter(
                name="selector",
                type="selector",
                required=True,
                description="CSS selector for the element",
            ),
            StepParameter(
                name="variable_name",
                type="string",
                required=False,
                description="Variable name to store the retrieved text",
            ),
            StepParameter(
                name="timeout",
                type="integer",
                required=False,
                default=TimeoutDefaults.BROWSER_ACTION,
                description="Maximum time to wait for element in milliseconds",
            ),
        ],
        timeout_category=TimeoutKeys.BROWSER_OPERATION,
    ),

    # ── Designer ──────────────────────────────────────────────────────────────

    StepTypeDefinition(
        step_type=StepType.DESIGNER_LAUNCH,
        description="Launch the Ignition Designer from a launcher file",
        parameters=[
            StepParameter(
                name="launcher_file",
                type="file",
                required=True,
                description="Path to the Designer launcher file (.jnlp or .exe)",
            ),
        ],
        timeout_category=TimeoutKeys.DESIGNER_LAUNCH,
    ),
    StepTypeDefinition(
        step_type=StepType.DESIGNER_LAUNCH_SHORTCUT,
        description="Launch Designer via Windows shortcut with automatic login",
        parameters=[
            StepParameter(
                name="designer_shortcut",
                type="string",
                required=True,
                description="Name or path of the Designer shortcut",
            ),
            StepParameter(
                name="project_name",
                type="string",
                required=True,
                description="Name of the project to open",
            ),
            StepParameter(
                name="gateway_credential",
                type="credential",
                required=False,
                description="Credential for Gateway login",
            ),
            StepParameter(
                name="username",
                type="string",
                required=False,
                description="Username for Gateway login (if not using credential)",
            ),
            StepParameter(
                name="password",
                type="string",
                required=False,
                description="Password for Gateway login (if not using credential)",
            ),
            StepParameter(
                name="timeout",
                type="integer",
                required=False,
                default=TimeoutDefaults.DESIGNER_LAUNCH,
                description="Maximum time to wait for Designer launch in seconds",
            ),
        ],
        timeout_category=TimeoutKeys.DESIGNER_LAUNCH,
    ),
    StepTypeDefinition(
        step_type=StepType.DESIGNER_LOGIN,
        description="Login to the Designer with username and password",
        parameters=[
            StepParameter(
                name="username",
                type="string",
                required=True,
                description="Username for Designer login",
            ),
            StepParameter(
                name="password",
                type="string",
                required=True,
                description="Password for Designer login",
            ),
            StepParameter(
                name="timeout",
                type="integer",
                required=False,
                default=30,
                description="Maximum time to wait for login in seconds",
            ),
        ],
        timeout_category=TimeoutKeys.DESIGNER_LAUNCH,
    ),
    StepTypeDefinition(
        step_type=StepType.DESIGNER_OPEN_PROJECT,
        description="Open a project in the Designer",
        parameters=[
            StepParameter(
                name="project_name",
                type="string",
                required=False,
                description="Name of the project to open (leave empty for manual selection)",
            ),
            StepParameter(
                name="timeout",
                type="integer",
                required=False,
                default=30,
                description="Maximum time to wait in seconds",
            ),
        ],
        timeout_category=TimeoutKeys.DESIGNER_LAUNCH,
    ),
    StepTypeDefinition(
        step_type=StepType.DESIGNER_CLOSE,
        description="Close the Designer application",
        parameters=[],
        timeout_category=None,
    ),
    StepTypeDefinition(
        step_type=StepType.DESIGNER_SCREENSHOT,
        description="Capture a screenshot of the Designer window",
        parameters=[
            StepParameter(
                name="name",
                type="string",
                required=False,
                description="Name for the screenshot file",
            ),
        ],
        timeout_category=None,
    ),
    StepTypeDefinition(
        step_type=StepType.DESIGNER_WAIT,
        description="Wait for the Designer window to appear",
        parameters=[
            StepParameter(
                name="timeout",
                type="integer",
                required=False,
                default=30,
                description="Maximum time to wait in seconds",
            ),
        ],
        timeout_category=TimeoutKeys.DESIGNER_LAUNCH,
    ),

    # ── Playbook ──────────────────────────────────────────────────────────────

    StepTypeDefinition(
        step_type=StepType.PLAYBOOK_RUN,
        description="Execute another playbook as a nested step",
        parameters=[
            StepParameter(
                name="playbook_path",
                type="string",
                required=True,
                description="Path to the playbook to execute",
            ),
            StepParameter(
                name="parameters",
                type="dict",
                required=False,
                description="Parameters to pass to the nested playbook",
            ),
        ],
        timeout_category=None,
    ),

    # ── Utility ───────────────────────────────────────────────────────────────

    StepTypeDefinition(
        step_type=StepType.SLEEP,
        description="Pause execution for a specified duration",
        parameters=[
            StepParameter(
                name="seconds",
                type="float",
                required=True,
                description="Number of seconds to sleep",
            ),
        ],
        timeout_category=None,
    ),
    StepTypeDefinition(
        step_type=StepType.LOG,
        description="Log a message during playbook execution",
        parameters=[
            StepParameter(
                name="message",
                type="string",
                required=True,
                description="Message to log",
            ),
            StepParameter(
                name="level",
                type="string",
                required=False,
                default="info",
                description="Log level",
                options=["debug", "info", "warning", "error"],
            ),
        ],
        timeout_category=None,
    ),
    StepTypeDefinition(
        step_type=StepType.SET_VARIABLE,
        description="Set a variable for use in subsequent steps",
        parameters=[
            StepParameter(
                name="name",
                type="string",
                required=True,
                description="Name of the variable",
            ),
            StepParameter(
                name="value",
                type="string",
                required=True,
                description="Value to assign to the variable",
            ),
        ],
        timeout_category=None,
    ),
    StepTypeDefinition(
        step_type=StepType.PYTHON,
        description="Execute a Python script (use with caution)",
        parameters=[
            StepParameter(
                name="script",
                type="string",
                required=True,
                description="Python code to execute",
            ),
        ],
        timeout_category=None,
    ),

    # ── Perspective FAT ───────────────────────────────────────────────────────

    StepTypeDefinition(
        step_type=StepType.PERSPECTIVE_DISCOVER_PAGE,
        description="Discover interactive components on a Perspective page",
        parameters=[
            StepParameter(
                name="selector",
                type="selector",
                required=False,
                default="body",
                description="Root selector to search within",
            ),
            StepParameter(
                name="types",
                type="list",
                required=False,
                description="List of component types to discover",
            ),
            StepParameter(
                name="exclude_selectors",
                type="list",
                required=False,
                description="Selectors to exclude from discovery",
            ),
        ],
        timeout_category=TimeoutKeys.BROWSER_OPERATION,
    ),
    StepTypeDefinition(
        step_type=StepType.PERSPECTIVE_EXTRACT_METADATA,
        description="Extract and enrich metadata for discovered components",
        parameters=[
            StepParameter(
                name="components",
                type="list",
                required=True,
                description="List of components from discover_page step",
            ),
        ],
        timeout_category=TimeoutKeys.BROWSER_OPERATION,
    ),
    StepTypeDefinition(
        step_type=StepType.PERSPECTIVE_EXECUTE_TEST_MANIFEST,
        description="Execute a test manifest against Perspective components",
        parameters=[
            StepParameter(
                name="manifest",
                type="list",
                required=True,
                description="List of test definitions to execute",
            ),
            StepParameter(
                name="capture_screenshots",
                type="boolean",
                required=False,
                default=True,
                description="Capture screenshots during testing",
            ),
            StepParameter(
                name="on_failure",
                type="string",
                required=False,
                default="continue",
                description="Action on test failure",
                options=["continue", "abort"],
            ),
            StepParameter(
                name="return_to_baseline",
                type="boolean",
                required=False,
                default=True,
                description="Return to baseline URL after each test",
            ),
            StepParameter(
                name="baseline_url",
                type="string",
                required=False,
                description="URL to return to after each test",
            ),
        ],
        timeout_category=TimeoutKeys.BROWSER_OPERATION,
    ),
    StepTypeDefinition(
        step_type=StepType.PERSPECTIVE_VERIFY_NAVIGATION,
        description="Verify that navigation occurred to expected URL/title",
        parameters=[
            StepParameter(
                name="expected_url_pattern",
                type="string",
                required=False,
                description="Expected URL pattern to match",
            ),
            StepParameter(
                name="expected_title_pattern",
                type="string",
                required=False,
                description="Expected page title pattern to match",
            ),
            StepParameter(
                name="timeout",
                type="integer",
                required=False,
                default=TimeoutDefaults.BROWSER_VERIFY,
                description="Maximum time to wait in milliseconds",
            ),
        ],
        timeout_category=TimeoutKeys.BROWSER_OPERATION,
    ),
    StepTypeDefinition(
        step_type=StepType.PERSPECTIVE_VERIFY_DOCK,
        description="Verify that a dock panel has opened",
        parameters=[
            StepParameter(
                name="dock_selector",
                type="selector",
                required=True,
                description="CSS selector for the dock element",
            ),
            StepParameter(
                name="timeout",
                type="integer",
                required=False,
                default=3000,
                description="Maximum time to wait in milliseconds",
            ),
        ],
        timeout_category=TimeoutKeys.BROWSER_OPERATION,
    ),
    StepTypeDefinition(
        step_type=StepType.PERSPECTIVE_VERIFY_WITH_AI,
        description="Use AI vision to verify UI elements in a screenshot",
        parameters=[
            StepParameter(
                name="prompt",
                type="string",
                required=True,
                description=(
                    "Verification prompt describing what to check "
                    "(e.g., 'Verify the login form is visible with username and password fields')"
                ),
            ),
            StepParameter(
                name="ai_api_key",
                type="credential",
                required=True,
                description="Anthropic API key for Claude Vision",
            ),
            StepParameter(
                name="selector",
                type="selector",
                required=False,
                description="CSS selector to screenshot specific element (optional, defaults to full page)",
            ),
            StepParameter(
                name="confidence_threshold",
                type="float",
                required=False,
                default=0.8,
                description="Minimum confidence (0.0-1.0) required to pass verification",
            ),
            StepParameter(
                name="ai_model",
                type="string",
                required=False,
                default="claude-sonnet-4-20250514",
                description="Claude model to use for verification",
                options=["claude-sonnet-4-20250514", "claude-opus-4-20250514"],
            ),
        ],
        timeout_category=TimeoutKeys.BROWSER_OPERATION,
    ),

    # ── FAT Reporting ─────────────────────────────────────────────────────────

    StepTypeDefinition(
        step_type=StepType.FAT_GENERATE_REPORT,
        description="Generate a Factory Acceptance Test report",
        parameters=[
            StepParameter(
                name="test_results",
                type="list",
                required=True,
                description="List of test results to include in report",
            ),
            StepParameter(
                name="title",
                type="string",
                required=False,
                default="FAT Report",
                description="Report title",
            ),
            StepParameter(
                name="include_screenshots",
                type="boolean",
                required=False,
                default=True,
                description="Include screenshots in the report",
            ),
        ],
        timeout_category=None,
    ),
    StepTypeDefinition(
        step_type=StepType.FAT_EXPORT_REPORT,
        description="Export a FAT report to file",
        parameters=[
            StepParameter(
                name="report",
                type="dict",
                required=True,
                description="Report data from generate_report step",
            ),
            StepParameter(
                name="output_path",
                type="string",
                required=True,
                description="Path to save the report",
            ),
            StepParameter(
                name="format",
                type="string",
                required=False,
                default="html",
                description="Output format",
                options=["html", "pdf", "json"],
            ),
        ],
        timeout_category=None,
    ),
]


# =============================================================================
# Lookup helpers
# =============================================================================

_REGISTRY_BY_TYPE: dict[StepType, StepTypeDefinition] = {
    entry.step_type: entry for entry in STEP_REGISTRY
}

_REGISTRY_BY_VALUE: dict[str, StepTypeDefinition] = {
    entry.type_value: entry for entry in STEP_REGISTRY
}


def get_step_definition(step_type: StepType) -> StepTypeDefinition | None:
    """Look up a step type definition by StepType enum value."""
    return _REGISTRY_BY_TYPE.get(step_type)


def get_step_definition_by_value(type_value: str) -> StepTypeDefinition | None:
    """Look up a step type definition by string value (e.g. 'gateway.login')."""
    return _REGISTRY_BY_VALUE.get(type_value)


def get_all_definitions() -> list[StepTypeDefinition]:
    """Return all step type definitions in registry order."""
    return STEP_REGISTRY


def get_definitions_for_timeout_category(category: str) -> list[StepTypeDefinition]:
    """Return all step type definitions that use the given timeout category."""
    return [d for d in STEP_REGISTRY if d.timeout_category == category]


def validate_registry_completeness() -> list[str]:
    """
    Validate that every StepType enum member has a registry entry.

    Returns a list of missing type values (empty list = registry is complete).
    Called at startup to catch missing entries early.
    """
    registered = {entry.step_type for entry in STEP_REGISTRY}
    missing = [st.value for st in StepType if st not in registered]
    return missing
