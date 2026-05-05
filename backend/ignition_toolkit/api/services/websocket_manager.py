"""
WebSocket Manager - Centralized WebSocket connection management

Manages WebSocket connections and broadcasts execution updates.
Supports message batching for high-frequency updates (screenshots).
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from typing import TYPE_CHECKING, Any

from fastapi import WebSocket

from ignition_toolkit.playbook.models import ExecutionStatus

if TYPE_CHECKING:
    from ignition_toolkit.playbook.models import ExecutionState

logger = logging.getLogger(__name__)

# Batching configuration
BATCH_SIZE_THRESHOLD = 10  # Batch messages when queue exceeds this
BATCH_FLUSH_INTERVAL = 0.1  # Flush batched messages every 100ms


class WebSocketManager:
    """
    Manages WebSocket connections and broadcasts

    Responsibilities:
    - Track active WebSocket connections
    - Broadcast execution state updates
    - Broadcast screenshot frames (with optional batching)
    - Handle connection cleanup

    Message batching is used for high-frequency messages like screenshots
    to reduce WebSocket overhead when many frames are sent rapidly.
    """

    def __init__(self, keepalive_interval: int = 15, enable_batching: bool = True):
        """
        Initialize WebSocket manager

        Args:
            keepalive_interval: Seconds between server keepalive pings (default: 15)
            enable_batching: Enable message batching for high-frequency updates (default: True)
        """
        self._connections: list[WebSocket] = []
        self._lock = asyncio.Lock()
        self._keepalive_tasks: dict[WebSocket, asyncio.Task] = {}
        self._keepalive_interval = keepalive_interval

        # Message batching state
        self._enable_batching = enable_batching
        self._message_queue: deque[dict] = deque()
        self._batch_task: asyncio.Task | None = None
        self._batch_lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        """
        Add new WebSocket connection

        Args:
            websocket: WebSocket connection to add
        """
        await websocket.accept()
        async with self._lock:
            self._connections.append(websocket)
            # Start keepalive task for this connection
            task = asyncio.create_task(self._keepalive_loop(websocket))
            self._keepalive_tasks[websocket] = task
            logger.info(f"WebSocket connected. Total connections: {len(self._connections)}")

    async def disconnect(self, websocket: WebSocket) -> None:
        """
        Remove WebSocket connection

        Args:
            websocket: WebSocket connection to remove
        """
        async with self._lock:
            if websocket in self._connections:
                self._connections.remove(websocket)
                # Cancel keepalive task for this connection
                if websocket in self._keepalive_tasks:
                    self._keepalive_tasks[websocket].cancel()
                    del self._keepalive_tasks[websocket]
                logger.info(
                    f"WebSocket disconnected. Total connections: {len(self._connections)}"
                )

    async def _keepalive_loop(self, websocket: WebSocket) -> None:
        """
        Send periodic keepalive pings to prevent connection timeout

        This runs independently of execution state to maintain connection
        during long-running operations (30-60+ seconds).

        Args:
            websocket: WebSocket connection to keep alive
        """
        from datetime import datetime

        try:
            while True:
                await asyncio.sleep(self._keepalive_interval)

                try:
                    # Send server-initiated keepalive ping
                    await websocket.send_json({
                        "type": "keepalive",
                        "timestamp": datetime.now().isoformat()
                    })
                    logger.debug(f"Sent keepalive to {websocket.client}")
                except Exception as e:
                    logger.warning(f"Failed to send keepalive to {websocket.client}: {e}")
                    # Connection is dead, will be cleaned up by disconnect()
                    break

        except asyncio.CancelledError:
            logger.debug(f"Keepalive task cancelled for {websocket.client}")
        except Exception as e:
            logger.exception(f"Error in keepalive loop for {websocket.client}: {e}")

    async def broadcast_execution_state(self, state: ExecutionState) -> None:
        """
        Broadcast execution state to all connected clients

        Args:
            state: ExecutionState object to broadcast
        """
        from ignition_toolkit.api.routers.models import StepResultResponse

        print(f"[WS] Broadcasting execution state: status={state.status.value if hasattr(state.status, 'value') else state.status}, step={state.current_step_index}, steps_count={len(state.step_results)}, connections={len(self._connections)}", flush=True)

        # Warn if broadcasting critical state with no connections
        status_value = state.status.value if hasattr(state.status, 'value') else state.status
        if len(self._connections) == 0 and status_value in [ExecutionStatus.CANCELLED.value, ExecutionStatus.FAILED.value]:
            logger.warning(
                f"[WARN]  CRITICAL: Broadcasting {status_value} status but NO WebSocket "
                f"connections active! Frontend will miss real-time update for execution {state.execution_id}"
            )

        # Convert step results to response format
        step_results = [
            StepResultResponse(
                step_id=result.step_id,
                step_name=result.step_name,
                status=result.status.value
                if hasattr(result.status, "value")
                else result.status,
                error=result.error,
                started_at=result.started_at,
                completed_at=result.completed_at,
                output=result.output,
                nested_steps=result.nested_steps,
            )
            for result in state.step_results
        ]

        # Frontend expects data wrapped in a "data" field
        message = {
            "type": "execution_update",
            "data": {
                "execution_id": state.execution_id,
                "playbook_name": state.playbook_name,
                "status": state.status.value if hasattr(state.status, "value") else state.status,
                "current_step_index": state.current_step_index,
                "total_steps": state.total_steps,
                "debug_mode": state.debug_mode,
                "started_at": state.started_at.isoformat() if state.started_at else None,
                "completed_at": state.completed_at.isoformat() if state.completed_at else None,
                "error": state.error,
                "domain": state.domain,
                "step_results": [
                    {
                        "step_id": sr.step_id,
                        "step_name": sr.step_name,
                        "status": sr.status,
                        "error": sr.error,
                        "started_at": sr.started_at.isoformat() if sr.started_at else None,
                        "completed_at": sr.completed_at.isoformat() if sr.completed_at else None,
                        "output": sr.output,
                        "nested_steps": sr.nested_steps,
                    }
                    for sr in step_results
                ],
            }
        }

        await self._broadcast(message)
        print("[WS] Broadcast complete", flush=True)

    async def broadcast_screenshot(self, execution_id: str, screenshot_b64: str) -> None:
        """
        Broadcast screenshot frame to all connected clients

        Screenshots use message batching when enabled to reduce overhead
        during rapid frame capture (e.g., 2+ FPS).

        Args:
            execution_id: Execution UUID
            screenshot_b64: Base64-encoded screenshot
        """
        from datetime import datetime

        message = {
            "type": "screenshot_frame",
            "data": {
                "executionId": execution_id,  # camelCase to match frontend
                "screenshot": screenshot_b64,
                "timestamp": datetime.now().isoformat(),
            },
        }
        # Use batching for screenshots (high frequency)
        await self._queue_message(message)

    async def broadcast_debug_context(
        self, execution_id: str, debug_context: dict[str, Any]
    ) -> None:
        """
        Broadcast debug context on failure

        Args:
            execution_id: Execution UUID
            debug_context: Debug context dictionary
        """
        message = {
            "type": "debug_context",
            "execution_id": execution_id,
            "context": debug_context,
        }
        await self._broadcast(message)

    async def _broadcast(self, message: dict) -> None:
        """
        Send message to all connected clients

        Args:
            message: Message dictionary to broadcast
        """
        disconnected = []

        async with self._lock:
            for ws in self._connections:
                try:
                    await ws.send_json(message)
                except Exception as e:
                    logger.warning(f"Failed to send message to WebSocket: {e}")
                    disconnected.append(ws)

            # Clean up disconnected clients
            for ws in disconnected:
                self._connections.remove(ws)

        if disconnected:
            logger.info(f"Removed {len(disconnected)} disconnected WebSocket(s)")

    async def close_all(self) -> None:
        """
        Close all WebSocket connections (called on shutdown)
        """
        logger.info("Closing all WebSocket connections...")

        # Stop batch task if running
        if self._batch_task:
            self._batch_task.cancel()
            try:
                await self._batch_task
            except asyncio.CancelledError:
                pass
            self._batch_task = None

        # Flush any remaining batched messages
        await self._flush_batch()

        async with self._lock:
            for ws in self._connections:
                try:
                    await ws.close()
                except Exception as e:
                    logger.warning(f"Error closing WebSocket: {e}")

            self._connections.clear()

        logger.info("All WebSocket connections closed")

    async def _queue_message(self, message: dict) -> None:
        """
        Queue a message for batched sending

        If batching is disabled or queue is small, sends immediately.
        Otherwise, queues the message and starts batch flush timer.

        Args:
            message: Message to queue
        """
        if not self._enable_batching:
            await self._broadcast(message)
            return

        async with self._batch_lock:
            self._message_queue.append(message)

            # If queue exceeds threshold, flush immediately
            if len(self._message_queue) >= BATCH_SIZE_THRESHOLD:
                await self._flush_batch()
            elif self._batch_task is None or self._batch_task.done():
                # Start flush timer if not already running
                self._batch_task = asyncio.create_task(self._batch_flush_timer())

    async def _batch_flush_timer(self) -> None:
        """
        Timer task that flushes batched messages after interval
        """
        try:
            await asyncio.sleep(BATCH_FLUSH_INTERVAL)
            await self._flush_batch()
        except asyncio.CancelledError:
            pass

    async def _flush_batch(self) -> None:
        """
        Flush all queued messages as a batch
        """
        async with self._batch_lock:
            if not self._message_queue:
                return

            # Collect all messages
            messages = list(self._message_queue)
            self._message_queue.clear()

        if len(messages) == 1:
            # Single message, send as-is
            await self._broadcast(messages[0])
        elif len(messages) > 1:
            # Multiple messages, send as batch
            batch_message = {
                "type": "batch",
                "messages": messages,
                "count": len(messages),
            }
            await self._broadcast(batch_message)
            logger.debug(f"Sent batched message with {len(messages)} items")

    def get_connection_count(self) -> int:
        """
        Get number of active connections

        Returns:
            Number of active WebSocket connections
        """
        return len(self._connections)
