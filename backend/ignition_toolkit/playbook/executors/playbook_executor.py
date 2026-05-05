"""
Playbook step handlers

Handles nested playbook execution using Strategy Pattern.
"""

import logging
from typing import Any

from ignition_toolkit.playbook.exceptions import StepExecutionError
from ignition_toolkit.playbook.executors.base import StepHandler
from ignition_toolkit.playbook.models import OnFailureAction, StepStatus

logger = logging.getLogger(__name__)


class PlaybookRunHandler(StepHandler):
    """
    Handle playbook.run step (nested playbook execution)

    This handler requires special initialization with the parent executor context
    to enable nested execution while sharing browser/gateway instances.
    """

    def __init__(self, parent_executor: Any):
        """
        Initialize playbook run handler

        Args:
            parent_executor: Reference to parent StepExecutor for nested execution
        """
        self.parent_executor = parent_executor

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        """
        Execute nested playbook as a single step (composable playbooks)

        Args:
            params: Resolved parameters including 'playbook' path

        Returns:
            Aggregated step output from nested playbook execution

        Raises:
            StepExecutionError: If playbook execution fails or validation fails
        """
        playbook_path = params.get("playbook")

        if not playbook_path:
            raise StepExecutionError("playbook", "Missing required parameter: playbook")

        # Convert to absolute path, searching user dir first then built-in
        from ignition_toolkit.core.paths import get_all_playbook_dirs
        from ignition_toolkit.playbook.loader import PlaybookLoader
        from ignition_toolkit.playbook.metadata import PlaybookMetadataStore

        metadata_store = PlaybookMetadataStore()

        # Resolve playbook path relative to playbooks root directory
        # Search user dir first so user-modified playbooks take priority
        full_path = None
        for playbooks_root in get_all_playbook_dirs():
            candidate = playbooks_root / playbook_path
            if candidate.exists():
                full_path = candidate
                break

        if full_path is None:
            raise StepExecutionError("playbook", f"Playbook not found: {playbook_path}")

        # Get relative path for metadata lookup (relative to playbooks root)
        relative_path = playbook_path

        # Verify that playbook is marked as verified
        metadata = metadata_store.get_metadata(relative_path)
        if not metadata.verified:
            raise StepExecutionError(
                "playbook",
                f"Playbook '{relative_path}' must be verified before it can be used as a step. "
                f"Mark it as verified via the UI 3-dot menu.",
            )

        # Check for circular dependencies (basic check)
        if hasattr(self.parent_executor, "_execution_stack"):
            if playbook_path in self.parent_executor._execution_stack:
                raise StepExecutionError(
                    "playbook",
                    f"Circular dependency detected: playbook '{playbook_path}' calls itself",
                )
        else:
            self.parent_executor._execution_stack = []

        # Add to execution stack
        self.parent_executor._execution_stack.append(playbook_path)

        # Check nesting depth
        MAX_NESTING_DEPTH = 3  # noqa: N806
        if len(self.parent_executor._execution_stack) > MAX_NESTING_DEPTH:
            self.parent_executor._execution_stack.pop()
            raise StepExecutionError(
                "playbook",
                f"Maximum nesting depth ({MAX_NESTING_DEPTH}) exceeded. "
                f"Current stack: {' -> '.join(self.parent_executor._execution_stack)}",
            )

        try:
            # Load nested playbook using static method
            nested_playbook = PlaybookLoader.load_from_file(full_path)

            # Extract parameters for child playbook (remove 'playbook' key)
            child_params = {k: v for k, v in params.items() if k != "playbook"}

            # Apply default values for missing optional parameters (Bug fix: nested playbooks need defaults)
            # This mirrors the logic in engine.py lines 239-245
            for param in nested_playbook.parameters:
                if param.name not in child_params and param.default is not None:
                    child_params[param.name] = param.default
                    logger.info(f"Applied default value for nested parameter '{param.name}': {param.default}")

            # Execute nested playbook using EXISTING browser and gateway from parent
            # This allows browser context to persist across nested calls
            logger.info(f"Executing nested playbook: {playbook_path}")
            logger.info(f"Child parameters: {child_params}")

            # Create a child StepExecutor that shares browser and gateway from parent
            from ignition_toolkit.playbook.parameters import ParameterResolver

            # Create step_results dictionary for nested playbook
            nested_step_results: dict[str, dict[str, Any]] = {}

            child_resolver = ParameterResolver(
                parameters=child_params,
                # Share the parent's variables dict by reference so any variable set
                # inside a nested playbook (e.g. session_logged_in in elev8_login) is
                # immediately visible to all callers up and down the chain.
                variables=self.parent_executor.parameter_resolver.variables
                if self.parent_executor.parameter_resolver
                else {},
                credential_vault=self.parent_executor.parameter_resolver.credential_vault
                if self.parent_executor.parameter_resolver
                else None,
                step_results=nested_step_results,
            )

            # Import StepExecutor here to avoid circular import at module level
            from ignition_toolkit.playbook.step_executor import StepExecutor

            child_executor = StepExecutor(
                gateway_client=self.parent_executor.gateway_client,  # Share parent's gateway client
                browser_manager=self.parent_executor.browser_manager,  # Share parent's browser manager
                designer_manager=self.parent_executor.designer_manager,  # Share parent's designer manager
                parameter_resolver=child_resolver,
                base_path=self.parent_executor.base_path,
                state_manager=self.parent_executor.state_manager,
                parent_engine=self.parent_executor.parent_engine,  # Pass parent engine for progress updates
            )
            child_executor._execution_stack = self.parent_executor._execution_stack.copy()

            # Execute all steps in the nested playbook
            nested_results = []
            nested_screenshots = []  # Track screenshots from nested execution
            live_nested_steps: list[dict] = []  # Live view broadcast to frontend

            async def _broadcast_nested(steps: list[dict]) -> None:
                if self.parent_executor.parent_engine:
                    try:
                        await self.parent_executor.parent_engine._update_nested_step_progress(steps)
                    except Exception as e:
                        logger.warning(f"Failed to broadcast nested step progress: {e}")

            for step in nested_playbook.steps:
                logger.info(f"Executing nested step: {step.name}")

                # Optimistically mark step as running before execution
                from datetime import datetime as _dt
                live_nested_steps.append({
                    "step_id": step.id,
                    "step_name": step.name,
                    "status": "running",
                    "started_at": _dt.now().isoformat(),
                    "completed_at": None,
                    "error": None,
                    "output": None,
                })
                await _broadcast_nested(live_nested_steps)

                step_result = await child_executor.execute_step(step)

                # Replace running entry with actual result
                live_nested_steps[-1] = {
                    "step_id": step_result.step_id,
                    "step_name": step_result.step_name,
                    "status": step_result.status.value if hasattr(step_result.status, "value") else str(step_result.status),
                    "started_at": step_result.started_at.isoformat() if step_result.started_at else None,
                    "completed_at": step_result.completed_at.isoformat() if step_result.completed_at else None,
                    "error": step_result.error,
                    "output": step_result.output,
                }
                await _broadcast_nested(live_nested_steps)

                # Store step output for nested playbook step references
                if step_result.output:
                    nested_step_results[step.id] = step_result.output

                # Extract screenshot paths from step result output
                if step_result.output and isinstance(step_result.output, dict):
                    screenshot = step_result.output.get("screenshot")
                    if screenshot and isinstance(screenshot, str):
                        nested_screenshots.append(screenshot)

                    nested_playbook_screenshots = step_result.output.get("screenshots", [])
                    if isinstance(nested_playbook_screenshots, list):
                        nested_screenshots.extend(nested_playbook_screenshots)

                nested_results.append({
                    "step_id": step.id,
                    "step_name": step.name,
                    "status": step_result.status.value if hasattr(step_result.status, "value") else str(step_result.status),
                })

                # Fail fast: abort nested playbook if a step fails (respecting on_failure)
                if step_result.status == StepStatus.FAILED:
                    if step.on_failure == OnFailureAction.CONTINUE:
                        logger.warning(
                            f"Nested step '{step.name}' failed in '{playbook_path}' "
                            f"(on_failure=continue, proceeding): {step_result.error}"
                        )
                    else:
                        logger.error(
                            f"Nested step '{step.name}' failed in '{playbook_path}': {step_result.error}"
                        )
                        raise StepExecutionError(
                            "playbook",
                            f"Nested playbook '{playbook_path}' failed at step '{step.name}': {step_result.error}",
                        )

            logger.info(f"Nested playbook '{playbook_path}' created {len(nested_screenshots)} screenshots")

            return {
                "playbook": playbook_path,
                "status": "completed",
                "steps_executed": len(nested_results),
                # Return summary of nested steps (nested steps are tracked separately in execution log)
                "steps": nested_results,
                # Track all screenshots created during nested execution (for cleanup on deletion)
                "screenshots": nested_screenshots,
            }

        finally:
            # Remove from execution stack
            self.parent_executor._execution_stack.pop()
