"""ARIA Event Bus — pub-sub with coalescing for Agent 3 triggers.

Coalescing: if N events fire within coalesce_window_s, Agent 3 runs once
with the latest state, not N times. Prevents thrashing during rapid
world-state changes (e.g., fire growth + new survivor within 500ms).

Heartbeat: fires 'heartbeat_check' if no other event has fired in
heartbeat_interval_s. Not a hard clock — resets on every publish().
"""

import asyncio
from datetime import datetime, timezone
from typing import Awaitable, Callable
import structlog

logger = structlog.get_logger()

Handler = Callable[[dict], Awaitable[None]]


class EventBus:
    def __init__(
        self,
        coalesce_window_s: float = 0.5,
        heartbeat_interval_s: float = 60.0,
    ):
        self._coalesce_window = coalesce_window_s
        self._heartbeat_interval = heartbeat_interval_s

        self._subscribers: dict[str, list[Handler]] = {}
        self._pending: list[dict] = []
        self._coalesce_task: asyncio.Task | None = None
        self._heartbeat_task: asyncio.Task | None = None
        self._last_event_at: float = 0.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def subscribe(self, event_type: str, handler: Handler) -> None:
        """Register a coroutine handler for an event type."""
        self._subscribers.setdefault(event_type, []).append(handler)

    async def publish(self, event_type: str, payload: dict) -> None:
        """Publish an event. Delivery is coalesced over coalesce_window_s."""
        self._pending.append({
            "type": event_type,
            "payload": payload,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        self._last_event_at = asyncio.get_event_loop().time()
        logger.debug("event_published", event_type=event_type)

        if self._coalesce_task is None or self._coalesce_task.done():
            self._coalesce_task = asyncio.create_task(self._coalesced_dispatch())

    async def start_heartbeat(
        self,
        incident_id: str,
        get_briefing_fn: Callable[[], dict],
    ) -> None:
        """Start the heartbeat task for this incident.

        get_briefing_fn is called at heartbeat time to get the current
        IncidentBriefing payload to include with the event.
        """
        self._heartbeat_task = asyncio.create_task(
            self._heartbeat_loop(incident_id, get_briefing_fn)
        )

    def stop(self) -> None:
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
        if self._coalesce_task and not self._coalesce_task.done():
            self._coalesce_task.cancel()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _coalesced_dispatch(self) -> None:
        await asyncio.sleep(self._coalesce_window)

        events = self._pending[:]
        self._pending.clear()

        if not events:
            return

        # Last event per type wins — avoids re-running on stale intermediate state
        latest_by_type: dict[str, dict] = {}
        for event in events:
            latest_by_type[event["type"]] = event

        logger.debug(
            "event_bus_dispatch",
            coalesced_count=len(events),
            unique_types=list(latest_by_type.keys()),
        )

        for event_type, event in latest_by_type.items():
            for handler in self._subscribers.get(event_type, []):
                try:
                    await handler(event["payload"])
                except Exception as exc:
                    logger.error(
                        "event_bus_handler_error",
                        event_type=event_type,
                        error=str(exc),
                    )

    async def _heartbeat_loop(
        self,
        incident_id: str,
        get_briefing_fn: Callable[[], dict],
    ) -> None:
        while True:
            await asyncio.sleep(self._heartbeat_interval)
            elapsed = asyncio.get_event_loop().time() - self._last_event_at
            if elapsed >= self._heartbeat_interval:
                briefing = get_briefing_fn()
                await self.publish(
                    "heartbeat_check",
                    {"incident_id": incident_id, "briefing": briefing},
                )
