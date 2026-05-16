"""Async pub-sub event bus with 500ms coalesce window and 60s heartbeat."""

import asyncio
from typing import Any, Callable

import structlog

logger = structlog.get_logger()

COALESCE_WINDOW_S = 0.5
HEARTBEAT_TIMEOUT_S = 60.0


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, list[Callable]] = {}
        self._pending: dict[str, Any] = {}
        self._coalesce_tasks: dict[str, asyncio.Task] = {}
        self._heartbeat_task: asyncio.Task | None = None
        self._last_event_time: float = 0.0

    def subscribe(self, event_type: str, handler: Callable) -> None:
        """Subscribe handler to event_type. Idempotent."""
        handlers = self._subscribers.setdefault(event_type, [])
        if handler not in handlers:
            handlers.append(handler)

    async def publish(self, event_type: str, payload: Any) -> None:
        """Publish event. Latest payload wins within coalesce window."""
        self._pending[event_type] = payload
        try:
            self._last_event_time = asyncio.get_event_loop().time()
        except RuntimeError:
            pass

        existing = self._coalesce_tasks.get(event_type)
        if existing and not existing.done():
            existing.cancel()

        self._coalesce_tasks[event_type] = asyncio.create_task(
            self._coalesce_dispatch(event_type)
        )

    async def _coalesce_dispatch(self, event_type: str) -> None:
        await asyncio.sleep(COALESCE_WINDOW_S)
        payload = self._pending.pop(event_type, None)
        if payload is None:
            return
        for handler in list(self._subscribers.get(event_type, [])):
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(payload)
                else:
                    handler(payload)
            except Exception as e:
                logger.warning("event_bus_handler_error", event_type=event_type, error=str(e))
        self._coalesce_tasks.pop(event_type, None)

    def start_heartbeat(self, handler: Callable) -> None:
        """Fire handler after HEARTBEAT_TIMEOUT_S of silence. Idempotent."""
        if self._heartbeat_task and not self._heartbeat_task.done():
            return
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop(handler))

    async def _heartbeat_loop(self, handler: Callable) -> None:
        while True:
            await asyncio.sleep(HEARTBEAT_TIMEOUT_S)
            try:
                now = asyncio.get_event_loop().time()
            except RuntimeError:
                return
            if now - self._last_event_time >= HEARTBEAT_TIMEOUT_S:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler({"type": "heartbeat_check"})
                    else:
                        handler({"type": "heartbeat_check"})
                except Exception as e:
                    logger.warning("heartbeat_error", error=str(e))
