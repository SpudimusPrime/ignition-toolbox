"""
Execution management routes

Handles playbook execution control, status tracking, and lifecycle management.
"""

import csv
import io
import logging
from datetime import datetime

import yaml
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse

from ignition_toolkit.api.routers.executions.helpers import (
    DEFAULT_EXECUTION_LIST_LIMIT,
    delete_screenshot_files,
    extract_screenshot_paths,
    get_active_engines,
    get_engine_or_404,
)
from ignition_toolkit.api.routers.executions.models import (
    BrowserClickRequest,
    PlaybookCodeUpdateRequest,
)
from ignition_toolkit.api.routers.models import (
    ExecutionRequest,
    ExecutionResponse,
    ExecutionStatusResponse,
    StepResultResponse,
)
from ignition_toolkit.api.services.execution_response_builder import ExecutionResponseBuilder
from ignition_toolkit.playbook.engine import PlaybookEngine
from ignition_toolkit.playbook.models import ExecutionStatus
from ignition_toolkit.storage import get_database

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/executions", tags=["executions"])


# ============================================================================
# Routes
# ============================================================================


@router.post("", response_model=ExecutionResponse)
async def start_execution(request: ExecutionRequest, background_tasks: BackgroundTasks):
    """
    Start playbook execution

    Simplified implementation using ExecutionService (replaces 11-step process with 3 lines).
    """
    from ignition_toolkit.api.app import app
    from ignition_toolkit.core.validation import PathValidator
    from ignition_toolkit.playbook.loader import PlaybookLoader

    try:
        # Get services from app state
        if not hasattr(app.state, "services"):
            raise HTTPException(
                status_code=503,
                detail="Application services not initialized",
            )

        services = app.state.services

        # Start execution using service layer (replaces 100+ lines of boilerplate)
        execution_id = await services.execution_service.start_execution(
            playbook_path=request.playbook_path,
            parameters=request.parameters,
            gateway_url=request.gateway_url,
            credential_name=request.credential_name,
            debug_mode=request.debug_mode,
            timeout_seconds=3600,  # 1 hour
            timeout_overrides=request.timeout_overrides,
        )

        # Load playbook to get name for response
        _, playbook_path = PathValidator.validate_and_resolve(request.playbook_path)
        playbook = PlaybookLoader.load_from_file(playbook_path)

        # Schedule cleanup background task
        background_tasks.add_task(services.execution_manager.cleanup_expired)

        return ExecutionResponse(
            execution_id=execution_id,
            playbook_name=playbook.name,
            status=ExecutionStatus.STARTED.value,
            message=f"Execution started with ID: {execution_id}",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error starting execution: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("", response_model=list[ExecutionStatusResponse])
async def list_executions(limit: int = DEFAULT_EXECUTION_LIST_LIMIT, status: str | None = None):
    """List all executions (active + recent completed from database)"""
    active_engines = get_active_engines()
    db = get_database()

    executions = []

    # Add active executions
    for exec_id, engine in active_engines.items():
        state = engine.get_current_execution()
        if not state:
            continue

        executions.append(ExecutionResponseBuilder.from_engine(exec_id, engine))

    # Add recent completed executions from database
    try:
        with db.session_scope() as session:
            from ignition_toolkit.storage.models import ExecutionModel

            query = session.query(ExecutionModel).order_by(ExecutionModel.started_at.desc())

            if status:
                query = query.filter(ExecutionModel.status == status)

            db_executions = query.limit(limit).all()
            logger.info(f"Loaded {len(db_executions)} executions from database")

            for db_exec in db_executions:
                executions.append(ExecutionResponseBuilder.from_database(db_exec))
    except Exception as e:
        logger.exception(f"Error loading executions from database: {e}")

    return executions[:limit]


@router.get("/{execution_id}", response_model=ExecutionStatusResponse)
async def get_execution_status(execution_id: str):
    """Get execution status and step results"""
    active_engines = get_active_engines()

    if execution_id in active_engines:
        engine = active_engines[execution_id]
        state = engine.get_current_execution()

        if state:
            # Engine has active state, return it
            return ExecutionResponseBuilder.from_engine(execution_id, engine)

    # Try to load from database
    db = get_database()
    try:
        with db.session_scope() as session:
            from ignition_toolkit.storage.models import ExecutionModel

            execution = (
                session.query(ExecutionModel)
                .filter(ExecutionModel.execution_id == execution_id)
                .first()
            )

            if execution:
                # Extract domain from execution metadata
                domain = None
                if execution.execution_metadata:
                    domain = execution.execution_metadata.get("domain")

                # Load step results from database relationship
                step_results = [
                    StepResultResponse(
                        step_id=step.step_id,
                        step_name=step.step_name,
                        status=step.status,
                        error=step.error_message,
                        started_at=step.started_at,
                        completed_at=step.completed_at,
                        output=step.output,
                    )
                    for step in execution.step_results
                ]

                return ExecutionStatusResponse(
                    execution_id=execution.execution_id,
                    playbook_name=execution.playbook_name,
                    status=execution.status,
                    started_at=execution.started_at,
                    completed_at=execution.completed_at,
                    current_step_index=len(step_results),
                    total_steps=len(step_results),
                    error=execution.error_message,
                    debug_mode=execution.execution_metadata.get("debug_mode", False) if execution.execution_metadata else False,
                    step_results=step_results,
                    domain=domain,
                )
    except Exception as e:
        logger.error(f"Error loading execution from database: {e}")

    raise HTTPException(status_code=404, detail=f"Execution {execution_id} not found")


@router.get("/{execution_id}/status", response_model=ExecutionStatusResponse)
async def get_execution_status_with_path(execution_id: str):
    """Get execution status (alternate endpoint for compatibility)"""
    return await get_execution_status(execution_id)


@router.post("/{execution_id}/pause")
async def pause_execution(execution_id: str, engine: PlaybookEngine = Depends(get_engine_or_404)):
    """Pause execution"""
    engine.pause()
    return {"message": "Execution paused", "execution_id": execution_id}


@router.post("/{execution_id}/resume")
async def resume_execution(execution_id: str, engine: PlaybookEngine = Depends(get_engine_or_404)):
    """Resume paused execution"""
    await engine.resume()
    return {"message": "Execution resumed", "execution_id": execution_id}


@router.post("/{execution_id}/skip")
async def skip_step(execution_id: str, engine: PlaybookEngine = Depends(get_engine_or_404)):
    """Skip current step and move to next"""
    await engine.skip_current_step()
    return {"message": "Step skipped", "execution_id": execution_id}


@router.post("/{execution_id}/skip_back")
async def skip_back_step(execution_id: str, engine: PlaybookEngine = Depends(get_engine_or_404)):
    """Skip back to previous step"""
    await engine.skip_back_step()
    return {"message": "Skipped back to previous step", "execution_id": execution_id}


async def _force_cancel_status(execution_id: str, execution_manager, app) -> None:
    """
    Force-update execution status to 'cancelled' in DB and broadcast via WebSocket.

    Called when the asyncio task had already completed before cancel was requested,
    meaning the CancelledError handler in run_execution() never fired.
    """
    # Update database
    db = get_database()
    if db:
        with db.session_scope() as session:
            from ignition_toolkit.storage import ExecutionModel

            execution = (
                session.query(ExecutionModel)
                .filter_by(execution_id=execution_id)
                .first()
            )
            if execution and execution.status in (ExecutionStatus.RUNNING.value, ExecutionStatus.PAUSED.value):
                execution.status = ExecutionStatus.CANCELLED.value
                execution.completed_at = datetime.now()
                session.commit()
                logger.info(f"Force-updated execution {execution_id} status to 'cancelled' in database")

    # Broadcast cancellation via WebSocket so frontend updates
    engine = execution_manager.get_engine(execution_id)
    if engine:
        execution_state = engine.get_current_execution()
        if execution_state:
            execution_state.status = ExecutionStatus.CANCELLED
            execution_state.completed_at = datetime.now()

            websocket_manager = app.state.services.websocket_manager
            await websocket_manager.broadcast_execution_state(execution_state)
            logger.info(f"Broadcasted forced cancellation via WebSocket for {execution_id}")


@router.post("/{execution_id}/cancel")
async def cancel_execution(execution_id: str):
    """Cancel execution"""
    from ignition_toolkit.api.app import app

    # Get execution manager from app services
    if not hasattr(app.state, "services"):
        raise HTTPException(
            status_code=503,
            detail="Application services not initialized",
        )

    execution_manager = app.state.services.execution_manager

    # Try to cancel active execution using ExecutionManager
    cancel_result = await execution_manager.cancel_execution(execution_id)

    if cancel_result is not None:
        # When the asyncio task was already done (completed/failed before cancel was requested),
        # the CancelledError handler in run_execution() never fires, so we must
        # update the database and broadcast the WebSocket update directly here.
        if cancel_result.get("task_was_done"):
            logger.info(f"Task was already done for {execution_id}, forcing status update")
            await _force_cancel_status(execution_id, execution_manager, app)

        logger.info(f"✅ Successfully cancelled execution {execution_id}")
        return {"message": "Execution cancelled", "execution_id": execution_id}

    # Execution not in memory - check if it exists in database (old execution from before server restart)
    db = get_database()
    if not db:
        raise HTTPException(status_code=404, detail=f"Execution {execution_id} not found")

    with db.session_scope() as session:
        from ignition_toolkit.storage import ExecutionModel

        execution = (
            session.query(ExecutionModel)
            .filter_by(execution_id=execution_id)
            .first()
        )

        if not execution:
            raise HTTPException(status_code=404, detail=f"Execution {execution_id} not found")

        # Mark old execution as cancelled in database
        if execution.status in [ExecutionStatus.RUNNING.value, ExecutionStatus.PAUSED.value]:
            logger.info(f"Cancelling database-only execution {execution_id} (started {execution.started_at})")
            execution.status = ExecutionStatus.CANCELLED.value
            execution.completed_at = datetime.now()
            execution.error_message = "Cancelled by user (execution was from before server restart)"
            session.commit()
            logger.info(f"Database-only execution {execution_id} marked as cancelled")
            return {"message": "Execution marked as cancelled in database", "execution_id": execution_id}
        else:
            # Execution already completed - return success instead of error for better UX
            logger.info(f"Cancel requested for already-completed execution {execution_id} (status: {execution.status})")
            return {
                "message": f"Execution already completed with status: {execution.status}",
                "execution_id": execution_id,
                "already_completed": True
            }


@router.get("/{execution_id}/playbook/code")
async def get_playbook_code(execution_id: str, engine: PlaybookEngine = Depends(get_engine_or_404)):
    """Get the YAML code for the playbook being executed"""
    # Read the original playbook file
    playbook_path = engine.get_playbook_path()
    if not playbook_path or not playbook_path.exists():
        raise HTTPException(status_code=404, detail="Playbook file not found")

    yaml_content = playbook_path.read_text(encoding='utf-8')

    state = engine.get_current_execution()
    playbook_name = state.playbook_name if state else "Unknown"

    return {
        "execution_id": execution_id,
        "playbook_path": str(playbook_path),
        "playbook_name": playbook_name,
        "code": yaml_content,
    }


@router.put("/{execution_id}/playbook/code")
async def update_playbook_code(
    execution_id: str,
    request: PlaybookCodeUpdateRequest,
    engine: PlaybookEngine = Depends(get_engine_or_404)
):
    """Update the playbook YAML during execution (for AI fixes)"""

    # Get playbook path
    playbook_path = engine.get_playbook_path()
    if not playbook_path or not playbook_path.exists():
        raise HTTPException(status_code=404, detail="Playbook file not found")

    # Validate YAML
    try:
        yaml.safe_load(request.code)
    except yaml.YAMLError as e:
        raise HTTPException(status_code=400, detail=f"Invalid YAML: {str(e)}")

    # Create backup
    backup_path = playbook_path.with_suffix(
        f".backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}.yaml"
    )
    backup_path.write_text(playbook_path.read_text(encoding='utf-8'), encoding='utf-8')
    logger.info(f"Created backup: {backup_path}")

    # Write new content
    playbook_path.write_text(request.code, encoding='utf-8')
    logger.info(f"Updated playbook code: {playbook_path}")

    return {
        "message": "Playbook code updated",
        "execution_id": execution_id,
        "playbook_path": str(playbook_path),
        "backup_path": str(backup_path.name),
    }


@router.get("/{execution_id}/report.csv")
async def get_execution_report_csv(execution_id: str):
    """Download report entries from an execution as CSV"""
    active_engines = get_active_engines()
    step_data: list[tuple[str, list[dict]]] = []  # (step_name, report_entries)
    playbook_name = "unknown"

    # Try active engine first
    if execution_id in active_engines:
        engine = active_engines[execution_id]
        state = engine.get_current_execution()
        if state:
            playbook_name = state.playbook_name
            for sr in state.step_results:
                if sr.output and sr.output.get("report_entries"):
                    step_data.append((sr.step_name, sr.output["report_entries"]))

    # Fall back to database
    if not step_data:
        db = get_database()
        try:
            with db.session_scope() as session:
                from ignition_toolkit.storage.models import ExecutionModel

                execution = (
                    session.query(ExecutionModel)
                    .filter(ExecutionModel.execution_id == execution_id)
                    .first()
                )
                if not execution:
                    raise HTTPException(status_code=404, detail=f"Execution {execution_id} not found")

                playbook_name = execution.playbook_name
                for step in execution.step_results:
                    if step.output and step.output.get("report_entries"):
                        step_data.append((step.step_name, step.output["report_entries"]))
        except HTTPException:
            raise
        except Exception as e:
            logger.exception(f"Error loading execution report from database: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    buf = io.StringIO()
    writer = csv.DictWriter(
        buf,
        fieldnames=[
            "execution_id", "playbook", "step_name", "component_id", "label",
            "declared_result", "actual_result", "matched", "skip_to_fired", "timestamp",
        ],
        extrasaction="ignore",
    )
    writer.writeheader()
    for step_name, entries in step_data:
        for entry in entries:
            writer.writerow({"execution_id": execution_id, "playbook": playbook_name, "step_name": step_name, **entry})

    buf.seek(0)
    filename = f"report_{execution_id[:8]}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.delete("/{execution_id}")
async def delete_execution(execution_id: str):
    """
    Delete execution from database and clean up related screenshots

    This removes:
    - Execution record from database
    - All step results for the execution
    - Screenshots captured during the execution
    """
    active_engines = get_active_engines()
    db = get_database()

    # Check if execution is still active - only block deletion if execution is actually running/paused
    if execution_id in active_engines:
        engine = active_engines[execution_id]
        state = engine.get_current_execution()
        if state and state.status in [ExecutionStatus.RUNNING, ExecutionStatus.PAUSED]:
            raise HTTPException(
                status_code=400,
                detail="Cannot delete active execution. Cancel or wait for completion first.",
            )

    # Delete from database
    try:
        with db.session_scope() as session:
            from ignition_toolkit.storage.models import ExecutionModel, StepResultModel

            execution = (
                session.query(ExecutionModel)
                .filter(ExecutionModel.execution_id == execution_id)
                .first()
            )

            if not execution:
                raise HTTPException(status_code=404, detail=f"Execution {execution_id} not found")

            # FIRST: Get screenshot paths from step results BEFORE deletion
            # Use SQLAlchemy relationship instead of query (execution_id is UUID string, not DB integer)
            step_results = execution.step_results
            screenshot_paths = extract_screenshot_paths(step_results)

            # NOTE: extract_screenshot_paths now handles nested playbook screenshots automatically
            # because playbook.run steps include a "screenshots" array in their output containing
            # all screenshots created during nested execution (supports up to depth 3 nesting)

            logger.info(f"Collected {len(screenshot_paths)} total screenshot paths (including nested playbooks)")

            # THEN: Delete related step results
            session.query(StepResultModel).filter(
                StepResultModel.execution_id == execution_id
            ).delete()

            # Delete execution
            session.delete(execution)
            logger.info(f"Deleted execution {execution_id} from database")

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error deleting execution from database: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

    # Clean up screenshots from step results artifacts
    deleted_screenshots = delete_screenshot_files(screenshot_paths)

    return {
        "message": "Execution deleted successfully",
        "execution_id": execution_id,
        "screenshots_deleted": deleted_screenshots,
    }


@router.post("/{execution_id}/debug/enable")
async def enable_debug_mode(execution_id: str, engine: PlaybookEngine = Depends(get_engine_or_404)):
    """Enable debug mode for an active execution"""
    from ignition_toolkit.api.app import app

    engine.state_manager.enable_debug_mode()

    logger.info(f"Debug mode enabled for execution {execution_id}")

    # Broadcast state update to WebSocket clients
    execution_state = engine.get_current_execution()
    if execution_state:
        # Update debug_mode flag in execution state
        execution_state.debug_mode = True
        # Use WebSocketManager from app services
        websocket_manager = app.state.services.websocket_manager
        await websocket_manager.broadcast_execution_state(execution_state)

    return {
        "status": "success",
        "execution_id": execution_id,
        "debug_mode": True,
        "message": "Debug mode enabled - execution will pause on next failure"
    }


@router.post("/{execution_id}/debug/disable")
async def disable_debug_mode(execution_id: str, engine: PlaybookEngine = Depends(get_engine_or_404)):
    """Disable debug mode for an active execution"""
    from ignition_toolkit.api.app import app

    engine.state_manager.disable_debug_mode()

    logger.info(f"Debug mode disabled for execution {execution_id}")

    # Broadcast state update to WebSocket clients
    execution_state = engine.get_current_execution()
    if execution_state:
        # Update debug_mode flag in execution state
        execution_state.debug_mode = False
        # Use WebSocketManager from app services
        websocket_manager = app.state.services.websocket_manager
        await websocket_manager.broadcast_execution_state(execution_state)

    return {
        "status": "success",
        "execution_id": execution_id,
        "debug_mode": False,
        "message": "Debug mode disabled"
    }


@router.post("/{execution_id}/browser/click")
async def click_in_browser(
    request: BrowserClickRequest,
    engine: PlaybookEngine = Depends(get_engine_or_404)
):
    """
    Click at specific coordinates in the browser during execution

    This allows users to interact with the browser during paused executions
    to help with debugging or manual intervention.

    Args:
        request: Browser click request with x and y coordinates
        engine: Active PlaybookEngine instance (injected)

    Returns:
        Success response with click coordinates

    Raises:
        HTTPException: If no browser available or click fails
    """
    # Check if browser manager exists
    if not engine.get_browser_manager():
        raise HTTPException(
            status_code=400, detail="No browser manager available for this execution"
        )

    try:
        # Perform click at coordinates
        await engine.get_browser_manager().click_at_coordinates(request.x, request.y)

        # Get execution state for execution_id
        state = engine.get_current_execution()
        execution_id = state.execution_id if state else "unknown"

        logger.info(
            f"Browser click executed at ({request.x}, {request.y}) for execution {execution_id}"
        )

        return {
            "status": "success",
            "message": f"Clicked at coordinates ({request.x}, {request.y})",
            "execution_id": execution_id,
            "coordinates": {"x": request.x, "y": request.y},
        }
    except Exception as e:
        logger.exception(f"Error clicking in browser: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to click in browser: {str(e)}"
        )
