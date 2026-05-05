"""
Playbook execution engine

Main orchestration logic for executing playbooks with state management.
"""

import asyncio
import logging
import uuid
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from ignition_toolkit.browser import BrowserManager
from ignition_toolkit.core.timeouts import TimeoutDefaults, TimeoutKeys
from ignition_toolkit.credentials import CredentialVault
from ignition_toolkit.designer import DesignerManager
from ignition_toolkit.gateway import GatewayClient
from ignition_toolkit.playbook.exceptions import PlaybookExecutionError
from ignition_toolkit.playbook.models import (
    ExecutionState,
    ExecutionStatus,
    OnFailureAction,
    ParameterType,
    Playbook,
    StepResult,
    StepStatus,
)
from ignition_toolkit.playbook.parameters import ParameterResolver
from ignition_toolkit.playbook.state_manager import StateManager
from ignition_toolkit.playbook.step_executor import StepExecutor
from ignition_toolkit.storage import Database, ExecutionModel, StepResultModel

logger = logging.getLogger(__name__)


class PlaybookEngine:
    """
    Execute playbooks with pause/resume/skip control

    Example:
        engine = PlaybookEngine(
            gateway_client=client,
            credential_vault=vault,
            database=db
        )

        # Execute playbook
        execution_state = await engine.execute_playbook(
            playbook,
            parameters={"gateway_url": "http://localhost:8088"}
        )

        # Control execution
        await engine.pause()
        await engine.resume()
        await engine.skip_current_step()
    """

    def __init__(
        self,
        gateway_client: GatewayClient | None = None,
        credential_vault: CredentialVault | None = None,
        database: Database | None = None,
        state_manager: StateManager | None = None,
        screenshot_callback: Callable[[str, str], None] | None = None,
        timeout_overrides: dict[str, int] | None = None,
    ):
        """
        Initialize playbook engine

        Args:
            gateway_client: Gateway client for gateway operations
            credential_vault: Credential vault for loading credentials
            database: Database for execution tracking
            state_manager: State manager for pause/resume/skip
            screenshot_callback: Async callback for screenshot frames (execution_id, screenshot_b64)
            timeout_overrides: Optional per-playbook timeout overrides
                - gateway_restart: Gateway restart timeout in seconds (default: 120)
                - module_install: Module installation timeout in seconds (default: 300)
                - browser_operation: Browser operation timeout in milliseconds (default: 30000)
                - designer_launch: Designer window detection timeout in seconds (default: 60)
        """
        self.gateway_client = gateway_client
        self.credential_vault = credential_vault
        self.database = database
        self.state_manager = state_manager or StateManager()
        self.screenshot_callback = screenshot_callback
        self.timeout_overrides = timeout_overrides or {}
        self._current_execution: ExecutionState | None = None
        self._current_playbook: Playbook | None = None
        self._playbook_path: Path | None = None
        self._update_callback: Callable[[ExecutionState], None] | None = None
        self._browser_manager: BrowserManager | None = None

    def get_gateway_restart_timeout(self) -> int:
        """Get gateway restart timeout in seconds (default: 120)"""
        return self.timeout_overrides.get(TimeoutKeys.GATEWAY_RESTART, TimeoutDefaults.GATEWAY_RESTART)

    def get_module_install_timeout(self) -> int:
        """Get module installation timeout in seconds (default: 300)"""
        return self.timeout_overrides.get(TimeoutKeys.MODULE_INSTALL, TimeoutDefaults.MODULE_INSTALL)

    def get_browser_operation_timeout(self) -> int:
        """Get browser operation timeout in milliseconds (default: 30000)"""
        return self.timeout_overrides.get(TimeoutKeys.BROWSER_OPERATION, TimeoutDefaults.BROWSER_ACTION)

    def get_designer_launch_timeout(self) -> int:
        """Get designer launch timeout in seconds (default: 60)"""
        return self.timeout_overrides.get(TimeoutKeys.DESIGNER_LAUNCH, TimeoutDefaults.DESIGNER_LAUNCH)

    def set_update_callback(self, callback: Callable[[ExecutionState], None]) -> None:
        """
        Set callback for execution updates

        Args:
            callback: Function to call on state updates
        """
        self._update_callback = callback

    def get_browser_manager(self) -> BrowserManager | None:
        """
        Get the browser manager instance if available

        Returns:
            BrowserManager instance or None if not initialized
        """
        return self._browser_manager

    def get_playbook_path(self) -> Path | None:
        """
        Get the path to the currently executing playbook

        Returns:
            Path to playbook file or None if not executing
        """
        return self._playbook_path

    def get_current_execution(self) -> ExecutionState | None:
        """
        Get the current execution state

        Returns:
            ExecutionState or None if not executing
        """
        return self._current_execution

    def get_current_playbook(self) -> Playbook | None:
        """
        Get the currently executing playbook

        Returns:
            Playbook or None if not executing
        """
        return self._current_playbook

    def _prepare_parameters(
        self, playbook: Playbook, parameters: dict[str, Any]
    ) -> tuple[ParameterResolver, dict[str, dict[str, Any]]]:
        """
        Validate and prepare parameters for execution

        Args:
            playbook: Playbook being executed
            parameters: User-provided parameter values

        Returns:
            Tuple of (ParameterResolver, step_results_dict)
        """
        # Validate parameters
        self._validate_parameters(playbook, parameters)

        # Preprocess credential-type parameters
        parameters = self._preprocess_credential_parameters(playbook, parameters)

        # Create step_results dictionary for tracking step outputs
        step_results_dict: dict[str, dict[str, Any]] = {}

        # Apply default values for missing optional parameters
        complete_parameters = parameters.copy()
        for param in playbook.parameters:
            if param.name not in complete_parameters and param.default is not None:
                complete_parameters[param.name] = param.default

        # Create parameter resolver
        resolver = ParameterResolver(
            credential_vault=self.credential_vault,
            parameters=complete_parameters,
            variables=self._current_execution.variables if self._current_execution else {},
            step_results=step_results_dict,
        )

        return resolver, step_results_dict

    async def _setup_resource_managers(
        self, playbook: Playbook, parameters: dict[str, Any], execution_id: str
    ) -> tuple[BrowserManager | None, "DesignerManager | None"]:
        """
        Set up browser and designer managers if needed

        Args:
            playbook: Playbook being executed
            parameters: Execution parameters
            execution_id: Execution ID for logging

        Returns:
            Tuple of (browser_manager, designer_manager)
        """
        browser_manager = None
        designer_manager = None

        # Extract download_path parameter if present
        download_path = parameters.get("download_path")
        downloads_dir = Path(download_path) if download_path else None

        # Set up browser manager if needed
        has_browser_steps = any(
            step.type.domain in ("browser", "perspective")
            for step in playbook.steps
        )
        playbook_domain = playbook.metadata.get('domain')
        needs_browser = playbook_domain in ("perspective", "gateway") or has_browser_steps

        if needs_browser:
            screenshot_frame_callback = None
            if self.screenshot_callback:
                async def screenshot_frame_callback(screenshot_b64: str):
                    await self.screenshot_callback(execution_id, screenshot_b64)

            browser_manager = BrowserManager(
                headless=True,
                screenshot_callback=screenshot_frame_callback,
                downloads_dir=downloads_dir,
            )
            await browser_manager.start()

            if screenshot_frame_callback:
                await browser_manager.start_screenshot_streaming()
                logger.info(f"Browser screenshot streaming started for execution {execution_id}")
            else:
                logger.info(f"Browser started without streaming for execution {execution_id}")

            self._browser_manager = browser_manager
        else:
            logger.debug(f"Skipping browser initialization (not needed for domain={playbook_domain})")

        # Set up designer manager if needed
        has_designer_steps = any(step.type.domain == "designer" for step in playbook.steps)
        if has_designer_steps:
            designer_install_path = parameters.get("designer_install_path")
            install_path = Path(designer_install_path) if designer_install_path else None

            designer_manager = DesignerManager(
                install_path=install_path,
                downloads_dir=downloads_dir,
            )
            await designer_manager.start()
            logger.info(f"Designer manager started for execution {execution_id}")

        return browser_manager, designer_manager

    def enable_debug(self, execution_id: str) -> None:
        """
        Enable debug mode for an execution (auto-pause after each step)

        Args:
            execution_id: The execution ID to enable debug mode for
        """
        self.state_manager.enable_debug_mode()

    async def execute_playbook(
        self,
        playbook: Playbook,
        parameters: dict[str, Any],
        base_path: Path | None = None,
        execution_id: str | None = None,
        playbook_path: Path | None = None,
    ) -> ExecutionState:
        """
        Execute playbook with parameters

        Args:
            playbook: Playbook to execute
            parameters: Parameter values
            base_path: Base path for resolving relative file paths
            execution_id: Optional execution ID (generated if not provided)

        Returns:
            Final execution state

        Raises:
            PlaybookExecutionError: If execution fails
        """
        # Create execution state FIRST (before validation)
        # This ensures ALL executions are tracked, even validation failures
        if execution_id is None:
            execution_id = str(uuid.uuid4())

        # Pre-populate all steps with pending status so UI can show them upfront
        initial_step_results = [
            StepResult(
                step_id=step.id,
                step_name=step.name,
                status=StepStatus.PENDING,
                error=None,
                started_at=None,
                completed_at=None,
            )
            for step in playbook.steps
        ]

        execution_state = ExecutionState(
            execution_id=execution_id,
            playbook_name=playbook.name,
            status=ExecutionStatus.RUNNING,
            started_at=datetime.now(),
            total_steps=len(playbook.steps),
            debug_mode=self.state_manager.is_debug_mode_enabled(),
            step_results=initial_step_results,
            domain=playbook.metadata.get("domain"),  # Include playbook domain
        )
        self._current_execution = execution_state
        self._current_playbook = playbook  # Store playbook for API access
        self._playbook_path = playbook_path  # Store path for code editing

        # Reset state manager
        self.state_manager.reset()

        # Save to database IMMEDIATELY (before validation)
        if self.database:
            await self._save_execution_start(execution_state, playbook, parameters)
        else:
            logger.warning("No database configured - execution will not be saved")

        # Initialize browser_manager and designer_manager to None BEFORE try block (scope issue)
        browser_manager = None
        designer_manager = None

        try:
            # Validate parameters (can fail, but state already saved)
            self._validate_parameters(playbook, parameters)

            # Preprocess credential-type parameters
            # Convert credential names (strings) to Credential objects
            parameters = self._preprocess_credential_parameters(playbook, parameters)

            # Create step_results dictionary for tracking step outputs (shared by reference)
            step_results_dict: dict[str, dict[str, Any]] = {}

            # Apply default values for missing optional parameters
            complete_parameters = parameters.copy()
            for param in playbook.parameters:
                if param.name not in complete_parameters and param.default is not None:
                    complete_parameters[param.name] = param.default

            # Create parameter resolver
            resolver = ParameterResolver(
                credential_vault=self.credential_vault,
                parameters=complete_parameters,
                variables=execution_state.variables,
                step_results=step_results_dict,
            )

            # Extract download_path parameter if present (supports local/network paths)
            download_path = parameters.get("download_path")
            downloads_dir = Path(download_path) if download_path else None

            # Create browser manager for Perspective/browser playbooks (NOT for Designer)
            has_browser_steps = any(
                step.type.domain in ("browser", "perspective")
                for step in playbook.steps
            )
            playbook_domain = playbook.metadata.get('domain')
            # Create browser for perspective, gateway domains, or any playbook with browser/perspective steps
            # This ensures nested playbooks can use the shared browser manager
            needs_browser = playbook_domain in ("perspective", "gateway") or has_browser_steps

            logger.debug(f"Playbook domain: {playbook_domain}, has_browser_steps: {has_browser_steps}, needs_browser: {needs_browser}")

            if needs_browser:
                # Create screenshot callback if available
                screenshot_frame_callback = None
                if self.screenshot_callback:
                    logger.debug("Creating browser manager with screenshot streaming")
                    async def screenshot_frame_callback(screenshot_b64: str):
                        await self.screenshot_callback(execution_id, screenshot_b64)
                else:
                    logger.debug("Creating browser manager without screenshot streaming")

                browser_manager = BrowserManager(
                    headless=True,
                    screenshot_callback=screenshot_frame_callback,
                    downloads_dir=downloads_dir,
                )
                await browser_manager.start()

                if screenshot_frame_callback:
                    await browser_manager.start_screenshot_streaming()
                    logger.info(f"Browser screenshot streaming started for execution {execution_id}")
                else:
                    logger.info(f"Browser started without streaming for execution {execution_id}")

                self._browser_manager = browser_manager  # Store reference for pause/resume
            else:
                logger.debug(f"Skipping browser initialization (not needed for domain={playbook_domain})")

            # Create designer manager if playbook has designer steps
            has_designer_steps = any(step.type.domain == "designer" for step in playbook.steps)
            if has_designer_steps:
                # Extract designer_install_path parameter if present
                designer_install_path = parameters.get("designer_install_path")
                install_path = Path(designer_install_path) if designer_install_path else None

                designer_manager = DesignerManager(
                    install_path=install_path,
                    downloads_dir=downloads_dir,
                )
                await designer_manager.start()
                logger.info(f"Designer manager started for execution {execution_id}")

            # Create step executor
            executor = StepExecutor(
                gateway_client=self.gateway_client,
                browser_manager=browser_manager,
                designer_manager=designer_manager,
                parameter_resolver=resolver,
                base_path=base_path,
                state_manager=self.state_manager,
                parent_engine=self,  # Pass self for nested execution updates
                timeout_overrides=self.timeout_overrides,
            )

            # Execute steps (using while loop to support skip back)
            step_index = 0
            logger.debug(f"Entering step execution loop ({len(playbook.steps)} steps)")
            while step_index < len(playbook.steps):
                step = playbook.steps[step_index]
                execution_state.current_step_index = step_index

                # Check control signals
                try:
                    await self.state_manager.check_control_signal()

                    # If execution was paused and has now resumed, update status to RUNNING
                    if execution_state.status == ExecutionStatus.PAUSED:
                        logger.info("Execution resumed - setting status to RUNNING")
                        execution_state.status = ExecutionStatus.RUNNING
                        await self._notify_update(execution_state)
                except asyncio.CancelledError:
                    execution_state.status = ExecutionStatus.CANCELLED
                    execution_state.completed_at = datetime.now()
                    await self._notify_update(execution_state)
                    if self.database:
                        await self._save_execution_end(execution_state)
                    return execution_state

                # Check if skip back requested
                if self.state_manager.is_skip_back_requested():
                    if step_index > 0:
                        logger.info(
                            f"Skipping back from step {step_index} to step {step_index - 1}"
                        )
                        step_index -= 1  # Go back 1 position
                        self.state_manager.clear_skip_back()
                        # Remove the last step result to re-execute it
                        if execution_state.step_results:
                            execution_state.step_results.pop()
                        await self._notify_update(execution_state)
                        continue  # Skip to the top of the loop to execute the previous step
                    else:
                        logger.warning("Cannot skip back - already at first step")
                        self.state_manager.clear_skip_back()

                # Check if skip requested
                if self.state_manager.is_skip_requested():
                    logger.info(f"Skipping step: {step.name}")
                    step_result = StepResult(
                        step_id=step.id,
                        step_name=step.name,
                        status=StepStatus.SKIPPED,
                        started_at=datetime.now(),
                        completed_at=datetime.now(),
                    )
                    execution_state.add_step_result(step_result)

                    # Keep current_step_index synchronized - use step_index
                    execution_state.current_step_index = step_index

                    self.state_manager.clear_skip()
                    await self._notify_update(execution_state)
                    if self.database:
                        await self._save_step_result(execution_state, step_result)
                    step_index += 1
                    continue

                # Execute step
                logger.debug(f"Executing step {step_index + 1}/{len(playbook.steps)}: {step.name}")
                logger.info(f"Executing step {step_index + 1}/{len(playbook.steps)}: {step.name}")

                # Create a RUNNING step result and notify before execution
                running_step_result = StepResult(
                    step_id=step.id,
                    step_name=step.name,
                    status=StepStatus.RUNNING,
                    started_at=datetime.now(),
                )
                execution_state.add_step_result(running_step_result)
                execution_state.current_step_index = step_index  # Update current step BEFORE notifying

                # DEBUG: Log step status before notify
                step_statuses = [(r.step_id, r.status.value) for r in execution_state.step_results]
                logger.info(f"[DEBUG] Before notify - Step {step_index + 1} ({step.id}): step_results statuses = {step_statuses}")

                await self._notify_update(execution_state)

                # Wrap step execution in try-except to catch cancellation during step execution
                try:
                    # Execute the step
                    step_result = await executor.execute_step(step)
                    logger.debug(f"Step execution complete: {step.name} - status={step_result.status}")

                    # Find and replace the running result with the completed result
                    for i, result in enumerate(execution_state.step_results):
                        if result.step_id == step.id and result.status == StepStatus.RUNNING:
                            execution_state.step_results[i] = step_result
                            break

                    # Store step output for {{ step.step_id.key }} references
                    if step_result.output:
                        step_results_dict[step.id] = step_result.output
                        logger.debug(f"Step {step.id} output stored: {list(step_result.output.keys())}")

                    # Handle set_variable step
                    if step.type.value == "utility.set_variable" and step_result.output:
                        var_name = step_result.output.get("variable")
                        var_value = step_result.output.get("value")
                        if var_name:
                            execution_state.variables[var_name] = var_value
                            logger.info(f"Set variable: {var_name} = {var_value}")

                    # Notify update
                    await self._notify_update(execution_state)

                    # Save to database
                    if self.database:
                        await self._save_step_result(execution_state, step_result)

                except asyncio.CancelledError:
                    logger.warning(f"Execution cancelled during step: {step.name}")
                    execution_state.status = ExecutionStatus.CANCELLED
                    execution_state.completed_at = datetime.now()
                    await self._notify_update(execution_state)
                    if self.database:
                        await self._save_execution_end(execution_state)
                    return execution_state

                # Auto-pause after each step in debug mode
                if self.state_manager.is_debug_mode_enabled():
                    logger.info("Debug mode: Auto-pausing after step completion")
                    await self.state_manager.pause()
                    execution_state.status = ExecutionStatus.PAUSED
                    await self._notify_update(execution_state)

                # Handle failure
                if step_result.status == StepStatus.FAILED:
                    logger.error(f"Step failed: {step.name} - {step_result.error}")

                    # In debug mode, pause on failure instead of aborting
                    if self.state_manager._debug_mode_enabled:
                        logger.info("Debug mode: Pausing on failed step for debugging")
                        execution_state.status = ExecutionStatus.PAUSED
                        step_result.error_message = f"Step failed in debug mode: {step_result.error}. Use AI assist or skip to continue."
                        await self.state_manager.pause()
                        await self._notify_update(execution_state)
                        # Wait for manual resume/skip instead of aborting
                        continue

                    if step.on_failure == OnFailureAction.ABORT:
                        execution_state.status = ExecutionStatus.FAILED
                        execution_state.error = f"Step '{step.id}' failed: {step_result.error}"
                        execution_state.completed_at = datetime.now()
                        await self._notify_update(execution_state)
                        if self.database:
                            await self._save_execution_end(execution_state)
                        return execution_state

                    elif step.on_failure == OnFailureAction.CONTINUE:
                        logger.warning("Continuing after failure (on_failure=continue)")
                        step_index += 1
                        continue

                    elif step.on_failure == OnFailureAction.ROLLBACK:
                        logger.warning("Rollback not yet implemented, aborting")
                        execution_state.status = ExecutionStatus.FAILED
                        execution_state.error = (
                            f"Step '{step.id}' failed (rollback requested but not implemented)"
                        )
                        execution_state.completed_at = datetime.now()
                        await self._notify_update(execution_state)
                        if self.database:
                            await self._save_execution_end(execution_state)
                        return execution_state

                # Move to next step (normal flow)
                step_index += 1

            # All steps completed
            execution_state.status = ExecutionStatus.COMPLETED
            execution_state.completed_at = datetime.now()
            logger.info(f"Playbook execution completed: {playbook.name}")

        except Exception as e:
            logger.exception(f"Playbook execution error: {e}")
            execution_state.status = ExecutionStatus.FAILED
            execution_state.error = str(e)
            execution_state.completed_at = datetime.now()

        finally:
            # Capture and broadcast final screenshot BEFORE closing browser
            if browser_manager and self.screenshot_callback:
                try:
                    # Get final screenshot in JPEG format (matching streaming format)
                    import base64
                    page = await browser_manager.get_page()
                    final_screenshot_bytes = await page.screenshot(type="jpeg", quality=80)
                    final_screenshot_b64 = base64.b64encode(final_screenshot_bytes).decode()

                    # Broadcast final screenshot
                    await self.screenshot_callback(execution_state.execution_id, final_screenshot_b64)
                    logger.info("Final screenshot captured and broadcast")
                except Exception as e:
                    logger.warning(f"Error capturing final screenshot: {e}")

            # Stop browser manager if created
            if browser_manager:
                try:
                    await browser_manager.stop_screenshot_streaming()
                    # Small delay to ensure streaming task fully stops before closing browser
                    await asyncio.sleep(0.2)
                    await browser_manager.stop()
                    logger.info("Browser screenshot streaming stopped")
                except Exception as e:
                    logger.warning(f"Error stopping browser manager: {e}")
                finally:
                    self._browser_manager = None  # Clear reference

            # Stop designer manager if created
            if designer_manager:
                try:
                    await designer_manager.stop()
                    logger.info("Designer manager stopped")
                except Exception as e:
                    logger.warning(f"Error stopping designer manager: {e}")

            # Notify final update
            await self._notify_update(execution_state)

            # Save to database
            if self.database:
                await self._save_execution_end(execution_state)

            self._current_execution = None

        return execution_state

    def _validate_parameters(self, playbook: Playbook, parameters: dict[str, Any]) -> None:
        """
        Validate provided parameters against playbook definition

        Args:
            playbook: Playbook definition
            parameters: Provided parameters

        Raises:
            PlaybookExecutionError: If parameters are invalid
        """
        for param_def in playbook.parameters:
            value = parameters.get(param_def.name, param_def.default)
            try:
                param_def.validate(value)
            except ValueError as e:
                raise PlaybookExecutionError(f"Parameter validation failed: {e}")

    def _preprocess_credential_parameters(self, playbook: Playbook, parameters: dict[str, Any]) -> dict[str, Any]:
        """
        Preprocess credential-type parameters

        Converts credential parameter values from string names to Credential objects
        by fetching them from the vault.

        Args:
            playbook: Playbook definition
            parameters: Provided parameters

        Returns:
            Updated parameters dict with Credential objects

        Raises:
            PlaybookExecutionError: If credential not found
        """
        result = parameters.copy()

        for param_def in playbook.parameters:
            # Check if this parameter is of type credential
            if param_def.type == ParameterType.CREDENTIAL:
                param_name = param_def.name
                credential_name = parameters.get(param_name)

                # If no value provided, try default
                if credential_name is None:
                    credential_name = param_def.default

                # If still no value and parameter is required, validation will catch it
                if credential_name is None:
                    continue

                # If value is already a Credential object, skip (for nested playbooks)
                from ignition_toolkit.credentials import Credential
                if isinstance(credential_name, Credential):
                    continue

                # Fetch credential from vault
                if not self.credential_vault:
                    raise PlaybookExecutionError(
                        f"Cannot resolve credential parameter '{param_name}': no credential vault configured"
                    )

                try:
                    credential = self.credential_vault.get_credential(credential_name)
                    if credential is None:
                        raise PlaybookExecutionError(
                            f"Credential '{credential_name}' not found in vault (parameter: {param_name})"
                        )
                    # Replace string with Credential object
                    result[param_name] = credential
                    logger.info(f"Resolved credential parameter '{param_name}' to credential '{credential_name}'")
                except Exception as e:
                    raise PlaybookExecutionError(
                        f"Error loading credential '{credential_name}' for parameter '{param_name}': {e}"
                    )

        return result

    async def _update_nested_step_progress(self, nested_steps: list[dict[str, Any]]) -> None:
        """
        Update the running playbook.run step's nested_steps list and broadcast.

        Called by PlaybookRunHandler before and after each child step so the
        frontend can watch child steps in real-time.

        Args:
            nested_steps: Full list of nested step result dicts accumulated so far
        """
        if not self._current_execution:
            return

        for step_result in self._current_execution.step_results:
            if step_result.status == StepStatus.RUNNING:
                step_result.nested_steps = nested_steps
                await self._notify_update(self._current_execution)
                logger.debug(f"Updated nested steps: {len(nested_steps)} steps")
                break

    async def _notify_update(self, execution_state: ExecutionState) -> None:
        """
        Notify callback of execution update

        Args:
            execution_state: Current execution state
        """
        if self._update_callback:
            try:
                if asyncio.iscoroutinefunction(self._update_callback):
                    await self._update_callback(execution_state)
                else:
                    self._update_callback(execution_state)
            except Exception as e:
                logger.exception(f"Error in update callback: {e}")

    async def _save_execution_start(
        self, execution_state: ExecutionState, playbook: Playbook, parameters: dict[str, Any]
    ) -> None:
        """Save execution start to database including initial pending steps"""
        try:
            logger.info(f"Saving execution start to database: {execution_state.execution_id}")
            with self.database.session_scope() as session:
                execution_model = ExecutionModel(
                    execution_id=execution_state.execution_id,  # Save UUID
                    playbook_name=execution_state.playbook_name,
                    status=execution_state.status.value,
                    started_at=execution_state.started_at,
                    config_data=parameters,
                    playbook_version=playbook.version,
                    execution_metadata={
                        "debug_mode": self.state_manager.is_debug_mode_enabled(),
                        "total_steps": len(playbook.steps),
                        "domain": playbook.metadata.get("domain"),  # Save playbook domain
                    },
                )
                session.add(execution_model)
                session.flush()  # Get the auto-generated ID

                # Save initial pending steps to database
                for step_result in execution_state.step_results:
                    step_model = StepResultModel(
                        execution_id=execution_model.id,
                        step_id=step_result.step_id,
                        step_name=step_result.step_name,
                        status=step_result.status.value,
                        started_at=step_result.started_at,
                        completed_at=step_result.completed_at,
                        error_message=step_result.error,
                        output=step_result.output,
                    )
                    session.add(step_model)

                # Store the database ID for later queries
                execution_state.db_execution_id = execution_model.id
                logger.info(f"Execution saved to database with ID: {execution_model.id} and {len(execution_state.step_results)} pending steps")
        except Exception as e:
            logger.exception(f"Error saving execution to database: {e}")

    async def _save_execution_end(self, execution_state: ExecutionState) -> None:
        """Save execution end to database"""
        try:
            logger.info(f"Saving execution end to database: {execution_state.execution_id}")
            with self.database.session_scope() as session:
                if not hasattr(execution_state, "db_execution_id"):
                    logger.warning(
                        f"No database execution ID found for {execution_state.execution_id}, skipping save"
                    )
                    return
                execution_model = (
                    session.query(ExecutionModel)
                    .filter_by(id=execution_state.db_execution_id)
                    .first()
                )
                if execution_model:
                    execution_model.status = execution_state.status.value
                    execution_model.completed_at = execution_state.completed_at
                    execution_model.error_message = execution_state.error
                    logger.info(
                        f"Execution end saved: {execution_state.execution_id} - Status: {execution_state.status.value}"
                    )
                else:
                    logger.warning(
                        f"Execution model not found in database for ID: {execution_state.db_execution_id}"
                    )
        except Exception as e:
            logger.exception(f"Error updating execution in database: {e}")

    async def _save_step_result(
        self, execution_state: ExecutionState, step_result: StepResult
    ) -> None:
        """Save step result to database"""
        try:
            if not hasattr(execution_state, "db_execution_id"):
                logger.warning("No database execution ID found, skipping step result save")
                return
            with self.database.session_scope() as session:
                step_model = StepResultModel(
                    execution_id=execution_state.db_execution_id,
                    step_id=step_result.step_id,
                    step_name=step_result.step_name,
                    status=step_result.status.value,
                    started_at=step_result.started_at,
                    completed_at=step_result.completed_at,
                    output=step_result.output,
                    error_message=step_result.error,
                )
                session.add(step_model)
        except Exception as e:
            logger.exception(f"Error saving step result to database: {e}")

    async def pause(self) -> None:
        """Pause execution after current step"""
        await self.state_manager.pause()
        # Also pause browser screenshot streaming (freezes current frame)
        if self._browser_manager:
            self._browser_manager.pause_screenshot_streaming()
            logger.info("Browser screenshot streaming paused")

    async def resume(self) -> None:
        """Resume paused execution"""
        await self.state_manager.resume()
        # Also resume browser screenshot streaming
        if self._browser_manager:
            self._browser_manager.resume_screenshot_streaming()
            logger.info("Browser screenshot streaming resumed")

    async def skip_current_step(self) -> None:
        """Skip current step"""
        await self.state_manager.skip_current_step()

    async def skip_back_step(self) -> None:
        """Skip back to previous step"""
        await self.state_manager.skip_back_step()

    async def cancel(self) -> None:
        """Cancel execution"""
        await self.state_manager.cancel()

        # Force-close browser to interrupt any ongoing operations
        if self._browser_manager:
            try:
                logger.info("Closing browser to force cancellation")
                await self._browser_manager.stop()
                self._browser_manager = None
            except Exception as e:
                logger.warning(f"Error closing browser during cancellation: {e}")

    def get_total_steps(self) -> int:
        """
        Get total number of steps in current playbook

        Returns:
            Number of steps, or 0 if no playbook loaded
        """
        return len(self._current_playbook.steps) if self._current_playbook else 0
