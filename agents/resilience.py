"""Resilience utilities — retry with exponential backoff for LLM API calls."""

import asyncio
import structlog

logger = structlog.get_logger()


async def retry_api_call(fn, max_retries: int = 3, base_delay: float = 2.0, context: str = "api_call"):
    """Retry an async callable with exponential backoff.

    Args:
        fn: Async callable (no arguments) to retry.
        max_retries: Maximum number of retry attempts after first failure.
        base_delay: Initial delay in seconds (doubles each retry).
        context: Label for log messages.

    Returns:
        The result of fn() on success.

    Raises:
        The last exception if all retries are exhausted.
    """
    last_exc = None
    for attempt in range(max_retries + 1):
        try:
            return await fn()
        except Exception as e:
            last_exc = e
            error_type = type(e).__name__
            error_msg = str(e)

            if attempt < max_retries:
                delay = base_delay * (2 ** attempt)
                logger.warning(
                    "api_retry",
                    context=context,
                    attempt=attempt + 1,
                    max_retries=max_retries,
                    delay_s=delay,
                    error_type=error_type,
                    error=error_msg[:200],
                )
                await asyncio.sleep(delay)
            else:
                logger.error(
                    "api_retries_exhausted",
                    context=context,
                    attempts=max_retries + 1,
                    error_type=error_type,
                    error=error_msg[:200],
                )
    raise last_exc
