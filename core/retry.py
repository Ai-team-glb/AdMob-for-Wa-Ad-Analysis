"""Generic async retry helper with linear backoff for recoverable failures."""
import asyncio
import functools
import logging

logger = logging.getLogger("admob_scraper")


class PermanentError(Exception):
    """Raised for errors that must NOT be retried (e.g. policy violations)."""


def async_retry(max_retries: int, backoff_seconds: float, exceptions=(Exception,)):
    """Decorator: retries an async function up to `max_retries` times on the
    given exception types, waiting `backoff_seconds * attempt` between tries.
    Re-raises the last exception if every attempt fails.
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            attempt = 0
            last_exc = None
            while attempt <= max_retries:
                try:
                    return await func(*args, **kwargs)
                except PermanentError:
                    raise
                except exceptions as exc:
                    last_exc = exc
                    attempt += 1
                    if attempt > max_retries:
                        break
                    wait = backoff_seconds * attempt
                    logger.warning(
                        "%s failed (attempt %d/%d): %s -- retrying in %.1fs",
                        func.__name__, attempt, max_retries, exc, wait,
                    )
                    await asyncio.sleep(wait)
            raise last_exc
        return wrapper
    return decorator
