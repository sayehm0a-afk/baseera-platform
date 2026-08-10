"""Bounded retry/backoff wrapper around a SAHMK provider's one-off
connectivity probe (SahmkMarketDataProvider.check_connectivity() /
SahmkFundamentalDataProvider.check_connectivity()).

Why this exists: SahmkClient._request() already retries 429/5xx/network
errors internally (tenacity, 3 attempts, see sahmk/client.py) -- but
provider_factory.py and fundamental_provider_factory.py wrap the *whole*
authenticate() call in a single `asyncio.wait_for(...,
timeout=SAHMK_PROBE_TIMEOUT_SECONDS)` with no retry of its own. That
outer timeout is a *per-attempt* budget, not a total retry budget:
production evidence (2026-08-08, two consecutive full-discovery runs)
showed the fundamentals ingestion job failing with "SAHMK connectivity
probe timed out" immediately after the several-minutes-long
historical_ohlcv job -- one slow response right after a burst of prior
SAHMK traffic was enough to raise StrictRealDataUnavailableError with
zero retries at this layer, even though SahmkClient's own internal
retry never got the chance to run to completion before the outer
envelope cut it off.

This module adds exactly one more bounded layer of retry, specific to
the class of failure that is genuinely transient (a probe timeout, an
exhausted-but-recoverable rate limit honoring Retry-After, or a
network-error-shaped SahmkRequestError -- see the status_code check
below) -- never for a response that means SAHMK is reachable and gave a
deterministic, permanent answer (401, a "still counts as authenticated"
403 PLAN_LIMIT, a missing API key, a genuine non-2xx business response
with a real status code, or a circuit breaker that is already open and
needs its own recovery_timeout to elapse, not more hammering).
"""

import asyncio
import logging
import random
from typing import Awaitable, Callable

from src.core.runtime.reliability_layer.circuit_breaker import CircuitBreakerOpenError
from src.market_data import config as market_data_config
from src.market_data.sahmk.exceptions import (
    SahmkAuthenticationError,
    SahmkConfigurationError,
    SahmkDailyQuotaExhaustedError,
    SahmkEntitlementError,
    SahmkRateLimitError,
    SahmkRequestError,
    SahmkResponseValidationError,
)
from src.market_data.sahmk.rate_limiter import SahmkUpstreamQuotaExhaustedError

logger = logging.getLogger(__name__)


class ProviderProbeTimeoutError(Exception):
    """Every retry attempt of the connectivity probe timed out."""


async def probe_connectivity_with_retry(
    check_connectivity: Callable[[], Awaitable[bool]],
    *,
    provider_label: str,
) -> bool:
    """Calls `check_connectivity` (a provider's own zero-arg bound
    method, e.g. `provider.check_connectivity` -- passed uncalled so a
    fresh coroutine is created per attempt, since a coroutine object
    cannot be awaited twice) with bounded retry/backoff for transient
    failures only.

    Returns whatever the eventually-successful attempt returned.
    Raises immediately, with no retry, for every permanent outcome
    (SahmkAuthenticationError, SahmkEntitlementError,
    SahmkConfigurationError, CircuitBreakerOpenError,
    SahmkResponseValidationError, or a SahmkRequestError that carries a
    real HTTP status code -- see the inline comment on that branch).
    Raises ProviderProbeTimeoutError once every attempt at a transient
    failure is exhausted.
    """
    max_attempts = max(1, market_data_config.get_provider_probe_max_attempts())
    per_attempt_timeout = market_data_config.get_provider_probe_timeout_seconds()
    base_delay = market_data_config.get_provider_probe_retry_base_delay_seconds()
    max_delay = market_data_config.get_provider_probe_retry_max_delay_seconds()

    last_exc: Exception = ProviderProbeTimeoutError(
        f"{provider_label}: connectivity probe did not complete."
    )

    for attempt in range(1, max_attempts + 1):
        logger.debug(
            "%s: connectivity probe attempt %d/%d (timeout=%.1fs).",
            provider_label, attempt, max_attempts, per_attempt_timeout,
        )
        delay = None
        try:
            result = await asyncio.wait_for(check_connectivity(), timeout=per_attempt_timeout)
            if attempt > 1:
                logger.info(
                    "%s: connectivity probe recovered on attempt %d/%d.",
                    provider_label, attempt, max_attempts,
                )
            return result
        except asyncio.TimeoutError:
            last_exc = ProviderProbeTimeoutError(
                f"{provider_label}: connectivity probe timed out after {per_attempt_timeout:.1f}s "
                f"(attempt {attempt}/{max_attempts})."
            )
            delay = _backoff_delay(attempt, base_delay, max_delay)
            _log_retry_or_exhausted(provider_label, "timeout", attempt, max_attempts, delay)
        except SahmkDailyQuotaExhaustedError:
            # SAHMK's own real evidence says today's account-wide quota
            # is spent for hours, not seconds -- retrying within this
            # function's few-second backoff window would just be
            # another wasted attempt against a known-exhausted budget
            # (SahmkClient.record_upstream_daily_exhaustion has already
            # recorded the real reset time by the time this is raised;
            # acquire() will short-circuit every other caller, this
            # process and every other worker, without even reaching the
            # network). Never retried here, same as the other
            # deterministic/permanent outcomes below.
            raise
        except SahmkUpstreamQuotaExhaustedError:
            # The rate limiter itself refused before any network call
            # was made, because a prior real 429 (this attempt or
            # another caller/worker entirely) already recorded SAHMK's
            # exhaustion evidence. Exactly as permanent as the case
            # above for the remainder of the hold window -- never
            # retried.
            raise
        except SahmkRateLimitError as exc:
            last_exc = exc
            delay = min(exc.retry_after, max_delay) if exc.retry_after else _backoff_delay(
                attempt, base_delay, max_delay
            )
            _log_retry_or_exhausted(provider_label, "rate_limited", attempt, max_attempts, delay)
        except (SahmkAuthenticationError, SahmkEntitlementError, SahmkConfigurationError):
            # Permanent, deterministic business outcomes -- an invalid
            # key, a plan limitation (already treated as "authenticated"
            # by check_connectivity() itself), or a missing key. Never
            # retried: attempting again would get the identical answer.
            raise
        except CircuitBreakerOpenError:
            # The breaker is already open from prior failures; retrying
            # immediately here would just hammer it again and defeats
            # its purpose -- it needs its own recovery_timeout to
            # elapse, not a faster retry loop at this layer.
            raise
        except SahmkResponseValidationError:
            # A 2xx with a missing/malformed required field is a
            # permanent, deterministic response-shape problem, not a
            # connectivity issue -- retrying would just get the same
            # malformed response again.
            raise
        except SahmkRequestError as exc:
            if exc.status_code is not None:
                # A genuine, deterministic non-2xx business response
                # (e.g. 400/404/405) -- SahmkClient's _handle_response
                # only sets status_code on this exact path; an
                # exhausted network-error or 5xx retry is raised with
                # status_code=None (see client.py's _request()). Never
                # blindly retried here -- requirement is "do not retry
                # permanent failures."
                raise
            last_exc = exc
            delay = _backoff_delay(attempt, base_delay, max_delay)
            _log_retry_or_exhausted(provider_label, "request_error", attempt, max_attempts, delay)

        if delay is not None and attempt < max_attempts:
            await asyncio.sleep(delay)

    logger.warning(
        "%s: connectivity probe exhausted all %d attempt(s); last error: %s",
        provider_label, max_attempts, last_exc,
    )
    raise last_exc


def _backoff_delay(attempt: int, base_delay: float, max_delay: float) -> float:
    """Exponential backoff with full jitter (uniform 0..computed_delay)
    -- the standard AWS-recommended jitter strategy, so multiple
    concurrent callers retrying the same transient SAHMK failure don't
    all retry in lockstep."""
    exponential = base_delay * (2 ** (attempt - 1))
    capped = min(exponential, max_delay)
    return random.uniform(0, capped)


def _log_retry_or_exhausted(
    provider_label: str, reason: str, attempt: int, max_attempts: int, delay: float
) -> None:
    if attempt < max_attempts:
        logger.info(
            "%s: connectivity probe attempt %d/%d failed (%s) -- retrying in %.2fs.",
            provider_label, attempt, max_attempts, reason, delay,
        )
    else:
        logger.warning(
            "%s: connectivity probe attempt %d/%d failed (%s) -- retries exhausted.",
            provider_label, attempt, max_attempts, reason,
        )
