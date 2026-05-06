"""
Step executor - Execute individual playbook steps using Strategy Pattern

Simplified executor that delegates to domain-specific handlers.
Reduced from 781 lines to ~250 lines (68% reduction).
"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from ignition_toolkit.browser import BrowserManager
from ignition_toolkit.core.timeouts import TimeoutDefaults, TimeoutKeys
from ignition_toolkit.designer import DesignerManager
from ignition_toolkit.gateway import GatewayClient
from ignition_toolkit.playbook.exceptions import StepExecutionError

# Import step handlers
from ignition_toolkit.playbook.executors import (
    BrowserClickHandler,
    BrowserFileUploadHandler,
    BrowserFillHandler,
    BrowserGetTextHandler,
    BrowserKeyboardHandler,
    BrowserNavigateHandler,
    BrowserScreenshotHandler,
    BrowserVerifyAttributeHandler,
    BrowserVerifyHandler,
    BrowserVerifyStateHandler,
    BrowserVerifyTextHandler,
    BrowserWaitHandler,
    DesignerCloseHandler,
    DesignerLaunchHandler,
    DesignerLaunchShortcutHandler,
    DesignerLoginHandler,
    DesignerOpenProjectHandler,
    DesignerScreenshotHandler,
    DesignerWaitHandler,
    FATExportReportHandler,
    # FAT reporting handlers
    FATGenerateReportHandler,
    GatewayGetHealthHandler,
    GatewayGetInfoHandler,
    GatewayGetProjectHandler,
    GatewayListModulesHandler,
    GatewayListProjectsHandler,
    GatewayLoginHandler,
    GatewayLogoutHandler,
    GatewayPingHandler,
    GatewayRestartHandler,
    GatewayUploadModuleHandler,
    GatewayWaitModuleHandler,
    GatewayWaitReadyHandler,
    # Perspective FAT handlers
    PerspectiveDiscoverPageHandler,
    PerspectiveExecuteTestManifestHandler,
    PerspectiveExtractMetadataHandler,
    PerspectiveVerifyDockHandler,
    PerspectiveVerifyNavigationHandler,
    # AI verification handlers
    PerspectiveVerifyWithAIHandler,
    PlaybookRunHandler,
    StepHandler,
    UtilityLogHandler,
    UtilityPythonHandler,
    UtilitySetVariableHandler,
    UtilitySleepHandler,
)
from ignition_toolkit.playbook.models import PlaybookStep, StepResult, StepStatus, StepType
from ignition_toolkit.playbook.parameters import ParameterResolver

logger = logging.getLogger(__name__)


class StepExecutor:
    """
    Execute individual playbook steps using Strategy Pattern

    Each step type is handled by a dedicated handler class for better separation of concerns.

    Example:
        executor = StepExecutor(gateway_client=client, resolver=resolver)
        result = await executor.execute_step(step)
    """

    def __init__(
        self,
        gateway_client: GatewayClient | None = None,
        browser_manager: BrowserManager | None = None,
        designer_manager: DesignerManager | None = None,
        parameter_resolver: ParameterResolver | None = None,
        base_path: Path | None = None,
        state_manager: Any | None = None,  # StateManager type hint causes circular import
        parent_engine: Any | None = None,  # Parent PlaybookEngine for nested execution
        timeout_overrides: dict[str, int] | None = None,  # Per-playbook timeout overrides
    ):
        """
        Initialize step executor with handler registry

        Args:
            gateway_client: Gateway client for gateway operations
            browser_manager: Browser manager for browser operations
            designer_manager: Designer manager for designer operations
            parameter_resolver: Parameter resolver for resolving references
            base_path: Base path for resolving relative file paths
            state_manager: State manager for pause/resume and debug mode
            parent_engine: Parent PlaybookEngine instance for nested execution updates
            timeout_overrides: Optional per-playbook timeout overrides
        """
        self.gateway_client = gateway_client
        self.browser_manager = browser_manager
        self.designer_manager = designer_manager
        self.parameter_resolver = parameter_resolver
        self.base_path = base_path or Path.cwd()
        self.state_manager = state_manager
        self.parent_engine = parent_engine
        self.timeout_overrides = timeout_overrides or {}

        # Initialize handler registry
        self._handlers = self._create_handler_registry()

    def _create_handler_registry(self) -> dict[StepType, StepHandler]:
        """
        Create registry mapping step types to handler instances

        Returns:
            Dictionary mapping StepType to StepHandler
        """
        handlers = {}

        # Gateway handlers
        if self.gateway_client:
            handlers[StepType.GATEWAY_LOGIN] = GatewayLoginHandler(self.gateway_client)
            handlers[StepType.GATEWAY_LOGOUT] = GatewayLogoutHandler(self.gateway_client)
            handlers[StepType.GATEWAY_PING] = GatewayPingHandler(self.gateway_client)
            handlers[StepType.GATEWAY_GET_INFO] = GatewayGetInfoHandler(self.gateway_client)
            handlers[StepType.GATEWAY_GET_HEALTH] = GatewayGetHealthHandler(self.gateway_client)
            handlers[StepType.GATEWAY_LIST_MODULES] = GatewayListModulesHandler(self.gateway_client)
            handlers[StepType.GATEWAY_UPLOAD_MODULE] = GatewayUploadModuleHandler(
                self.gateway_client, self.parameter_resolver, self.base_path
            )
            handlers[StepType.GATEWAY_WAIT_MODULE] = GatewayWaitModuleHandler(
                self.gateway_client,
                default_timeout=self.timeout_overrides.get(TimeoutKeys.MODULE_INSTALL, TimeoutDefaults.MODULE_INSTALL),
            )
            handlers[StepType.GATEWAY_LIST_PROJECTS] = GatewayListProjectsHandler(self.gateway_client)
            handlers[StepType.GATEWAY_GET_PROJECT] = GatewayGetProjectHandler(self.gateway_client)
            handlers[StepType.GATEWAY_RESTART] = GatewayRestartHandler(
                self.gateway_client,
                default_timeout=self.timeout_overrides.get(TimeoutKeys.GATEWAY_RESTART, TimeoutDefaults.GATEWAY_RESTART),
            )
            handlers[StepType.GATEWAY_WAIT_READY] = GatewayWaitReadyHandler(
                self.gateway_client,
                default_timeout=self.timeout_overrides.get(TimeoutKeys.GATEWAY_RESTART, TimeoutDefaults.GATEWAY_RESTART),
            )

        # Browser handlers
        if self.browser_manager:
            browser_timeout = self.timeout_overrides.get(TimeoutKeys.BROWSER_OPERATION, TimeoutDefaults.BROWSER_ACTION)
            verify_timeout = self.timeout_overrides.get(TimeoutKeys.BROWSER_OPERATION, TimeoutDefaults.BROWSER_VERIFY)
            handlers[StepType.BROWSER_NAVIGATE] = BrowserNavigateHandler(self.browser_manager)
            handlers[StepType.BROWSER_CLICK] = BrowserClickHandler(self.browser_manager, default_timeout=browser_timeout)
            handlers[StepType.BROWSER_FILL] = BrowserFillHandler(self.browser_manager, default_timeout=browser_timeout)
            handlers[StepType.BROWSER_KEYBOARD] = BrowserKeyboardHandler(self.browser_manager)
            handlers[StepType.BROWSER_FILE_UPLOAD] = BrowserFileUploadHandler(self.browser_manager, default_timeout=browser_timeout)
            handlers[StepType.BROWSER_SCREENSHOT] = BrowserScreenshotHandler(self.browser_manager)
            handlers[StepType.BROWSER_WAIT] = BrowserWaitHandler(self.browser_manager, default_timeout=browser_timeout)
            handlers[StepType.BROWSER_VERIFY] = BrowserVerifyHandler(self.browser_manager, default_timeout=verify_timeout)
            handlers[StepType.BROWSER_VERIFY_TEXT] = BrowserVerifyTextHandler(self.browser_manager, default_timeout=verify_timeout)
            handlers[StepType.BROWSER_VERIFY_ATTRIBUTE] = BrowserVerifyAttributeHandler(self.browser_manager, default_timeout=verify_timeout)
            handlers[StepType.BROWSER_VERIFY_STATE] = BrowserVerifyStateHandler(self.browser_manager, default_timeout=verify_timeout)
            handlers[StepType.BROWSER_GET_TEXT] = BrowserGetTextHandler(self.browser_manager, default_timeout=browser_timeout)

        # Designer handlers
        if self.designer_manager:
            handlers[StepType.DESIGNER_LAUNCH] = DesignerLaunchHandler(self.designer_manager)
            handlers[StepType.DESIGNER_LAUNCH_SHORTCUT] = DesignerLaunchShortcutHandler(self.designer_manager)
            handlers[StepType.DESIGNER_LOGIN] = DesignerLoginHandler(self.designer_manager)
            handlers[StepType.DESIGNER_OPEN_PROJECT] = DesignerOpenProjectHandler(self.designer_manager)
            handlers[StepType.DESIGNER_CLOSE] = DesignerCloseHandler(self.designer_manager)
            handlers[StepType.DESIGNER_SCREENSHOT] = DesignerScreenshotHandler(self.designer_manager)
            handlers[StepType.DESIGNER_WAIT] = DesignerWaitHandler(self.designer_manager)

        # Playbook handler (nested playbooks)
        handlers[StepType.PLAYBOOK_RUN] = PlaybookRunHandler(parent_executor=self)

        # Utility handlers (always available)
        handlers[StepType.SLEEP] = UtilitySleepHandler()
        handlers[StepType.LOG] = UtilityLogHandler()
        handlers[StepType.SET_VARIABLE] = UtilitySetVariableHandler()
        handlers[StepType.PYTHON] = UtilityPythonHandler(self.parameter_resolver, self.timeout_overrides)

        # Perspective FAT handlers (require browser manager)
        if self.browser_manager:
            handlers[StepType.PERSPECTIVE_DISCOVER_PAGE] = PerspectiveDiscoverPageHandler(self.browser_manager)
            handlers[StepType.PERSPECTIVE_EXTRACT_METADATA] = PerspectiveExtractMetadataHandler(self.browser_manager)
            handlers[StepType.PERSPECTIVE_EXECUTE_TEST_MANIFEST] = PerspectiveExecuteTestManifestHandler(self.browser_manager, parameter_resolver=self.parameter_resolver)
            handlers[StepType.PERSPECTIVE_VERIFY_NAVIGATION] = PerspectiveVerifyNavigationHandler(self.browser_manager)
            handlers[StepType.PERSPECTIVE_VERIFY_DOCK] = PerspectiveVerifyDockHandler(self.browser_manager)
            handlers[StepType.PERSPECTIVE_VERIFY_WITH_AI] = PerspectiveVerifyWithAIHandler(self.browser_manager)

        # FAT reporting handlers (always available)
        handlers[StepType.FAT_GENERATE_REPORT] = FATGenerateReportHandler()
        handlers[StepType.FAT_EXPORT_REPORT] = FATExportReportHandler()

        return handlers

    async def execute_step(self, step: PlaybookStep) -> StepResult:
        """
        Execute a single step with retries

        Args:
            step: Step to execute

        Returns:
            Step execution result
        """
        # Evaluate skip_if before doing anything else
        if step.skip_if and self.parameter_resolver:
            if self.parameter_resolver.resolve_skip_if(step.skip_if):
                logger.info(f"Skipping step '{step.id}' — skip_if condition was truthy: {step.skip_if}")
                return StepResult(
                    step_id=step.id,
                    step_name=step.name,
                    status=StepStatus.SKIPPED,
                    started_at=datetime.now(),
                    completed_at=datetime.now(),
                    output={"skipped": True, "reason": f"skip_if: {step.skip_if}"},
                )

        result = StepResult(
            step_id=step.id,
            step_name=step.name,
            status=StepStatus.RUNNING,
            started_at=datetime.now(),
        )

        retry_count = 0
        last_error = None

        while retry_count <= step.retry_count:
            try:
                # Execute step with timeout
                output = await asyncio.wait_for(self._execute_step_impl(step), timeout=step.timeout)

                # Success
                result.status = StepStatus.COMPLETED
                result.completed_at = datetime.now()
                result.output = output
                result.retry_count = retry_count
                return result

            except asyncio.TimeoutError:
                last_error = f"Step timed out after {step.timeout} seconds"
                logger.warning(f"Step {step.id} timed out (attempt {retry_count + 1})")

            except Exception as e:
                last_error = str(e)
                logger.warning(f"Step {step.id} failed (attempt {retry_count + 1}): {e}")

            # Check if debug mode is enabled - if so, pause on first failure
            if (
                self.state_manager
                and self.state_manager.is_debug_mode_enabled()
                and retry_count == 0  # Only on first failure
            ):
                logger.info("Debug mode enabled - capturing context and pausing")
                debug_context = await self._capture_debug_context(step, last_error)
                await self.state_manager.trigger_debug_pause(debug_context)

                # Mark step as failed and return (no retries in debug mode)
                result.status = StepStatus.FAILED
                result.completed_at = datetime.now()
                result.error = last_error
                result.retry_count = 0
                return result

            # Increment retry count
            retry_count += 1

            # Wait before retry (unless this was the last attempt)
            if retry_count <= step.retry_count:
                logger.info(f"Retrying step {step.id} in {step.retry_delay} seconds...")
                await asyncio.sleep(step.retry_delay)

        # All retries exhausted
        result.status = StepStatus.FAILED
        result.completed_at = datetime.now()
        result.error = last_error
        result.retry_count = retry_count - 1
        return result

    async def _capture_debug_context(self, step: PlaybookStep, error: str) -> dict[str, Any]:
        """
        Capture debug context on failure

        Args:
            step: Failed step
            error: Error message

        Returns:
            Debug context dictionary
        """
        context = {
            "step_id": step.id,
            "step_name": step.name,
            "step_type": step.type.value,
            "step_parameters": step.parameters,
            "error": error,
            "timestamp": datetime.now().isoformat(),
        }

        # Capture screenshot and HTML if browser step
        if self.browser_manager and step.type.domain == "browser":
            try:
                context["screenshot_base64"] = await self.browser_manager.get_screenshot_base64()
                context["page_html"] = await self.browser_manager.get_page_html()
                logger.info("Captured screenshot and HTML for debug context")
            except Exception as e:
                logger.warning(f"Failed to capture screenshot/HTML: {e}")
                context["capture_error"] = str(e)

        return context

    async def _execute_step_impl(self, step: PlaybookStep) -> dict[str, Any]:
        """
        Execute step implementation using handler registry

        Args:
            step: Step to execute

        Returns:
            Step output data

        Raises:
            StepExecutionError: If step fails or no handler found
        """
        # Resolve parameters
        resolved_params = {}
        if self.parameter_resolver:
            resolved_params = self.parameter_resolver.resolve(step.parameters)
        else:
            resolved_params = step.parameters

        # Get handler from registry
        handler = self._handlers.get(step.type)

        if handler is None:
            raise StepExecutionError(step.id, f"No handler registered for step type: {step.type}")

        # Execute using handler
        try:
            return await handler.execute(resolved_params)
        except StepExecutionError:
            # Re-raise StepExecutionErrors as-is
            raise
        except Exception as e:
            # Wrap other exceptions
            raise StepExecutionError(step.type.domain, f"{step.type.value} operation failed: {e}")
