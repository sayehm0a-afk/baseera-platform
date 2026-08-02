"""SAHMK pre-flight gate: the hard "prove real data before scanning"
check strict real-data mode requires before any full-market scan may
begin (see src.market_data.config.is_strict_real_data_enabled).

Deliberately reuses provider_factory's existing selection/
authentication logic rather than writing a second SAHMK client call --
this module only interprets that result under strict mode's rules and
adds one real sample request + a real DB round-trip on top, exactly
the checks a "can Basirah actually run today" gate needs and nothing
more. No secret value is ever read into a field of PreflightResult or
included in `reason`.
"""

import logging
from dataclasses import asdict, dataclass
from typing import Any, Callable, Dict, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from src.market_data import config as market_data_config
from src.market_data import provider_factory
from src.market_data.strict_mode import StrictRealDataUnavailableError

logger = logging.getLogger(__name__)

DATA_SOURCE_SAHMK_REAL = "SAHMK_REAL"

# A large-cap symbol expected to exist in every real SAHMK universe --
# used only as the pre-flight's own sample request, never persisted as
# scan output.
_DEFAULT_SAMPLE_SYMBOL = "2222"


@dataclass(frozen=True)
class PreflightResult:
    ready: bool
    provider: str
    authenticated: bool
    strict_real_data: bool
    synthetic_allowed: bool
    connectivity: str  # "SUCCESS" | "FAILED" | "NOT_ATTEMPTED"
    database_ok: bool
    sample_symbol: Optional[str]
    sample_timestamp: Optional[str]
    data_source: Optional[str]
    reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


async def run_sahmk_preflight(
    session_factory: Callable[[], Session],
    sample_symbol: str = _DEFAULT_SAMPLE_SYMBOL,
) -> PreflightResult:
    """Never raises -- every failure mode is reported as
    `ready=False` with a precise, secret-free `reason`, so a caller
    (scan_job_runner, the /health/market-data route) always gets a
    structured answer instead of having to catch an exception."""
    strict = market_data_config.is_strict_real_data_enabled()
    synthetic_allowed = market_data_config.is_synthetic_data_allowed()
    configured_provider = market_data_config.get_configured_provider_name()

    if not strict:
        return PreflightResult(
            ready=False, provider=configured_provider, authenticated=False,
            strict_real_data=False, synthetic_allowed=synthetic_allowed,
            connectivity="NOT_ATTEMPTED", database_ok=False, sample_symbol=None,
            sample_timestamp=None, data_source=None,
            reason="STRICT_REAL_DATA is not enabled -- the pre-flight gate requires strict mode.",
        )

    if not market_data_config.has_sahmk_credentials():
        return PreflightResult(
            ready=False, provider="sahmk", authenticated=False, strict_real_data=True,
            synthetic_allowed=False, connectivity="FAILED", database_ok=False,
            sample_symbol=None, sample_timestamp=None, data_source=None,
            reason="SAHMK_API_KEY is not configured.",
        )

    database_ok = _check_database(session_factory)
    if not database_ok:
        return PreflightResult(
            ready=False, provider="sahmk", authenticated=False, strict_real_data=True,
            synthetic_allowed=False, connectivity="NOT_ATTEMPTED", database_ok=False,
            sample_symbol=None, sample_timestamp=None, data_source=None,
            reason="Database connectivity check failed.",
        )

    try:
        provider = await provider_factory.get_market_data_provider(force_refresh=True)
    except StrictRealDataUnavailableError as exc:
        return PreflightResult(
            ready=False, provider="sahmk", authenticated=False, strict_real_data=True,
            synthetic_allowed=False, connectivity="FAILED", database_ok=database_ok,
            sample_symbol=None, sample_timestamp=None, data_source=None,
            reason=exc.reason,
        )

    kind = provider_factory.get_last_selected_provider_kind()
    if kind != "sahmk" or getattr(provider, "is_synthetic", True):
        # Defense in depth only -- provider_factory should already have
        # raised StrictRealDataUnavailableError instead of reaching here.
        return PreflightResult(
            ready=False, provider=kind or "unknown", authenticated=False, strict_real_data=True,
            synthetic_allowed=False, connectivity="FAILED", database_ok=database_ok,
            sample_symbol=None, sample_timestamp=None, data_source=None,
            reason="Provider selection did not resolve to a real SAHMK provider under strict mode.",
        )

    sample_price = None
    sample_timestamp: Optional[str] = None
    try:
        get_latest_quote = getattr(provider, "get_latest_quote", None)
        if get_latest_quote is not None:
            quote = await get_latest_quote(sample_symbol)
            sample_price = quote.get("price")
            sample_timestamp = quote.get("timestamp")
        if sample_price is None:
            bar = await provider.get_stock_data(sample_symbol)
            sample_price = bar.get("close")
            sample_timestamp = sample_timestamp or bar.get("date") or bar.get("timestamp")
    except Exception as exc:  # noqa: BLE001 -- any real-request failure fails the gate, never falls back
        logger.warning("SAHMK pre-flight sample request failed: %s: %s", type(exc).__name__, exc)
        return PreflightResult(
            ready=False, provider="sahmk", authenticated=True, strict_real_data=True,
            synthetic_allowed=False, connectivity="FAILED", database_ok=database_ok,
            sample_symbol=sample_symbol, sample_timestamp=None, data_source=None,
            reason=f"Real SAHMK sample request failed: {type(exc).__name__}",
        )

    if sample_price is None:
        return PreflightResult(
            ready=False, provider="sahmk", authenticated=True, strict_real_data=True,
            synthetic_allowed=False, connectivity="FAILED", database_ok=database_ok,
            sample_symbol=sample_symbol, sample_timestamp=sample_timestamp, data_source=None,
            reason="SAHMK responded but returned no recognizable real price field.",
        )

    return PreflightResult(
        ready=True, provider="sahmk", authenticated=True, strict_real_data=True,
        synthetic_allowed=False, connectivity="SUCCESS", database_ok=database_ok,
        sample_symbol=sample_symbol, sample_timestamp=sample_timestamp,
        data_source=DATA_SOURCE_SAHMK_REAL, reason=None,
    )


def _check_database(session_factory: Callable[[], Session]) -> bool:
    """A real, write-capable transaction (`SELECT 1` + commit), not
    just a ping -- proves the scan can actually persist a result, not
    only that a socket to Postgres exists."""
    session = session_factory()
    try:
        session.execute(text("SELECT 1"))
        session.commit()
        return True
    except Exception:  # noqa: BLE001
        logger.warning("SAHMK pre-flight database check failed.", exc_info=True)
        return False
    finally:
        session.close()
