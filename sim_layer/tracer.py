"""Mock Omium tracer. Structural match to real SDK — swap this file in V2."""

import structlog

logger = structlog.get_logger()


class Span:
    def __init__(self, name: str, attrs: dict):
        self._name = name
        self._attrs = dict(attrs)

    def set_attribute(self, key: str, value) -> None:
        self._attrs[key] = value

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
