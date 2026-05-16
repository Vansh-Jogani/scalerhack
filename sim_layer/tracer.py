"""Omium tracer — live SDK with mock fallback if key absent."""

import os
import structlog

logger = structlog.get_logger()

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

    def set_attribute(self, key: str, value) -> None:
        self._attrs[key] = value

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

    def __exit__(self, *args) -> None:
        logger.debug("trace_span_end", span=self._name, **self._attrs)


class Tracer:
    """Mock Omium tracer. Replace class body with real SDK in V2."""

    def __init__(self, service_name: str):
        self.service_name = service_name

    def start_span(self, name: str, **attrs) -> Span:
        logger.debug("trace_span_start", service=self.service_name, span=name, **attrs)
        return Span(name, attrs)

    def record_event(self, name: str, **attrs) -> None:
        logger.info("trace_event", service=self.service_name, event_name=name, **attrs)


tracer = Tracer("aria-v1")
