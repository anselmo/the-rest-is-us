import time
from dataclasses import dataclass
from typing import Callable, TypeVar

from hn_signal.config import log

T = TypeVar("T")


@dataclass(frozen=True)
class RetryConfig:
    """Configuration for retry behavior."""

    max_attempts: int
    base_delay: float  # seconds
    max_delay: float
    backoff_factor: float
    retryable: Callable[[Exception], bool]


def retry(fn: Callable[..., T], config: RetryConfig, description: str = "") -> T:
    """Call fn(), retrying on retryable exceptions per config.

    Uses exponential backoff: delay = min(base_delay * backoff_factor^attempt, max_delay)
    """
    for attempt in range(config.max_attempts):
        try:
            return fn()
        except Exception as e:
            if not config.retryable(e) or attempt == config.max_attempts - 1:
                raise
            delay = min(
                config.base_delay * (config.backoff_factor**attempt), config.max_delay
            )
            log.warning(
                "%s: attempt %d/%d failed (%s), retrying in %.0fs",
                description or "retry",
                attempt + 1,
                config.max_attempts,
                e,
                delay,
            )
            time.sleep(delay)
    raise RuntimeError("unreachable")  # satisfies type checker


# Pre-configured profiles
RATE_LIMIT = RetryConfig(
    max_attempts=6,
    base_delay=65.0,
    max_delay=65.0,
    backoff_factor=1.0,  # fixed delay for rate limits
    retryable=lambda e: "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e),
)

NETWORK = RetryConfig(
    max_attempts=3,
    base_delay=2.0,
    max_delay=30.0,
    backoff_factor=2.0,  # exponential: 2s, 4s, 8s
    retryable=lambda e: isinstance(e, (ConnectionError, TimeoutError, OSError)),
)
