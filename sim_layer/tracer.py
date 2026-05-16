<<<<<<< HEAD
"""Omium tracer — live SDK with mock fallback if key absent."""
=======
"""ARIA Tracer — structured observability spans for the agent pipeline.

Emits trace spans for: agent invocations, tool calls, webhook events,
and orchestrator state transitions. Writes JSON traces to traces/ directory.
Positions for Omium SDK swap.
"""

import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
>>>>>>> 24c6382f974245ec571eddb1af70efedb54b5a47

import os
import structlog

logger = structlog.get_logger()

<<<<<<< HEAD
try:
    import omium
    omium.init(
        api_key=os.getenv("OMIUM_API_KEY"),
        project="aria-v1",
        api_base_url="https://app.omium.ai",
    )
    logger.info("omium_live", project="aria-v1")
except Exception as _omium_err:
    logger.warning("omium_init_failed", error=str(_omium_err))


class Span:
    def __init__(self, name: str, attrs: dict):
        self._name = name
        self._attrs = dict(attrs)
        self.events: list[dict] = []
=======
TRACES_DIR = Path("traces")
TRACES_DIR.mkdir(exist_ok=True)


class Span:
    """A single trace span representing one unit of work."""
>>>>>>> 24c6382f974245ec571eddb1af70efedb54b5a47

    def __init__(self, name: str, span_type: str, parent_id: str | None = None, metadata: dict | None = None):
        self.span_id = str(uuid.uuid4())[:12]
        self.parent_id = parent_id
        self.trace_id = None
        self.name = name
        self.span_type = span_type
        self.start_time = time.time()
        self.end_time: float | None = None
        self.status = "in_progress"
        self.metadata = metadata or {}
        self.events: list[dict] = []

<<<<<<< HEAD
    def add_event(self, name: str, attributes: dict | None = None) -> None:
        """Append a timestamped event to this span."""
        import datetime
        self.events.append({
            "name": name,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "attributes": attributes or {},
        })
        logger.debug("trace_span_event", span=self._name, event=name, **(attributes or {}))

    def __enter__(self) -> "Span":
        return self
=======
    def add_event(self, name: str, data: Any = None) -> None:
        self.events.append({
            "name": name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": data,
        })
>>>>>>> 24c6382f974245ec571eddb1af70efedb54b5a47

    def end(self, status: str = "ok") -> None:
        self.end_time = time.time()
        self.status = status

    def to_dict(self) -> dict:
        return {
            "span_id": self.span_id,
            "parent_id": self.parent_id,
            "trace_id": self.trace_id,
            "name": self.name,
            "type": self.span_type,
            "start_time": datetime.fromtimestamp(self.start_time, tz=timezone.utc).isoformat(),
            "end_time": datetime.fromtimestamp(self.end_time, tz=timezone.utc).isoformat() if self.end_time else None,
            "duration_ms": round((self.end_time - self.start_time) * 1000) if self.end_time else None,
            "status": self.status,
            "metadata": self.metadata,
            "events": self.events,
        }


class Trace:
    """A collection of causally-linked spans representing one workflow execution."""

    def __init__(self, name: str):
        self.trace_id = str(uuid.uuid4())[:16]
        self.name = name
        self.spans: list[Span] = []
        self.start_time = datetime.now(timezone.utc).isoformat()

    def start_span(self, name: str, span_type: str, parent_id: str | None = None, metadata: dict | None = None) -> Span:
        span = Span(name, span_type, parent_id=parent_id, metadata=metadata)
        span.trace_id = self.trace_id
        self.spans.append(span)
        return span

<<<<<<< HEAD
    def record_event(self, name: str, **attrs) -> None:
        logger.info("trace_event", service=self.service_name, event_name=name, **attrs)
=======
    def to_dict(self) -> dict:
        return {
            "trace_id": self.trace_id,
            "name": self.name,
            "start_time": self.start_time,
            "spans": [s.to_dict() for s in self.spans],
            "span_count": len(self.spans),
        }

    def save(self) -> Path:
        filename = f"{self.trace_id}_{self.name.replace(' ', '_')}.json"
        path = TRACES_DIR / filename
        path.write_text(json.dumps(self.to_dict(), indent=2))
        logger.info("trace_saved", path=str(path), spans=len(self.spans))
        return path
>>>>>>> 24c6382f974245ec571eddb1af70efedb54b5a47


class ARIATracer:
    """Global tracer singleton for the ARIA pipeline."""

    def __init__(self):
        self.active_traces: dict[str, Trace] = {}

    def start_trace(self, incident_id: str) -> Trace:
        trace = Trace(f"incident_{incident_id}")
        self.active_traces[incident_id] = trace
        logger.info("trace_started", trace_id=trace.trace_id, incident_id=incident_id)
        return trace

    def get_trace(self, incident_id: str) -> Trace | None:
        return self.active_traces.get(incident_id)

    def end_trace(self, incident_id: str) -> Trace | None:
        trace = self.active_traces.pop(incident_id, None)
        if trace:
            trace.save()
        return trace

    def trace_agent_start(self, incident_id: str, agent_name: str, metadata: dict | None = None) -> Span | None:
        trace = self.get_trace(incident_id)
        if not trace:
            return None
        span = trace.start_span(f"{agent_name}_invocation", "agent", metadata=metadata)
        return span

    def trace_tool_call(self, incident_id: str, tool_name: str, input_data: dict, parent_span_id: str | None = None) -> Span | None:
        trace = self.get_trace(incident_id)
        if not trace:
            return None
        span = trace.start_span(f"tool:{tool_name}", "tool_call", parent_id=parent_span_id, metadata={"input": input_data})
        return span

    def trace_webhook(self, source: str, alert_type: str, metadata: dict | None = None) -> Span | None:
        for trace in self.active_traces.values():
            span = trace.start_span(f"webhook:{source}/{alert_type}", "webhook", metadata=metadata)
            span.end("ok")
            return span
        return None

    def trace_state_transition(self, incident_id: str, from_state: str, to_state: str) -> None:
        trace = self.get_trace(incident_id)
        if not trace:
            return
        span = trace.start_span(f"transition:{from_state}→{to_state}", "orchestrator")
        span.end("ok")


tracer = ARIATracer()
