#!/usr/bin/env python3
"""EXACTLY-ONE-REQUEST real SAHMK Historical OHLCV diagnostic.

Forensic, one-shot tooling in the same family as verify_sahmk_*.py
(scripts/verify_sahmk_historical_deep_dive.py etc.) -- real, unmocked,
invoked only by a dedicated workflow_dispatch workflow, using the real
production SAHMK_API_KEY. Unlike those scripts, this one is written to
survive and REPORT a real error response (401/403/429/5xx/other) in
full detail via SahmkError.sanitized_provider_detail() (PR #109), not
just a 200.

HARD SAFETY GUARANTEE: this script makes AT MOST ONE real wire request
to SAHMK, no matter what the response is. SahmkClient._request()'s own
internal retry (tenacity, up to 3 attempts on 429-without-daily-quota-
wording or 5xx/network errors) is neutralized WITHOUT modifying
SahmkClient at all: this script monkeypatches only the *instance's own*
`_send` method (a plain attribute override on one object in this
process's memory -- src/market_data/sahmk/client.py itself is
byte-for-byte unmodified, nothing here is committed as a code change to
the client) so any 2nd+ invocation of `_send` raises a purely local,
zero-network _DiagnosticBudgetExceeded instead of touching the network
again. The real, single wire call still goes through the exact same
production call path (SahmkClient.get_historical -> SahmkClient._request
-> SahmkRateLimiter.acquire() -> ... -> SahmkClient._send), so Basirah's
own internal quota bookkeeping is updated exactly as it would be for a
real production call -- this is not a bypass of accounting, only of a
hypothetical 2nd/3rd wire attempt.

Also performs one read-only DB query (mirrors
ingest_historical_ohlcv._latest_bar_date() exactly) to compute the same
incremental-vs-backfill date range Basirah's own scheduler would use
for this symbol right now -- zero SAHMK cost, needed only to reproduce
the real production request shape precisely rather than guess a date
range.

Never prints the API key (SahmkClient's own header value is never
touched or read by this script) or any other secret.
"""

import asyncio
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

SYMBOL = os.environ.get("DIAGNOSTIC_SYMBOL", "1213")
BACKFILL_DAYS = 90  # matches ingest_historical_ohlcv.py's default


class _DiagnosticBudgetExceeded(Exception):
    """Raised locally (zero network I/O) if anything -- SahmkClient's
    own tenacity retry included -- tries to make a second real wire
    request during this diagnostic. Never raised by production code;
    exists only in this script's guard wrapper."""


def _print(line: str = "") -> None:
    print(str(line))


async def run() -> int:
    from src.core.db.database import get_session_factory
    from src.domain.models import PriceBar, Stock, Timeframe
    from src.market_data.sahmk.client import SahmkClient
    from src.market_data.sahmk.exceptions import SahmkError
    from src.market_data.sahmk.rate_limiter import get_default_rate_limiter
    from sqlalchemy import func

    _print("=" * 72)
    _print("SAHMK EXACTLY-ONE-REQUEST HISTORICAL DIAGNOSTIC (real, unmocked)")
    _print(f"Symbol: {SYMBOL}")
    _print("=" * 72)

    # --- Phase A: read-only, zero-SAHMK-cost -- reproduce the exact
    # production date-range decision for this symbol -------------------
    session_factory = get_session_factory()
    session = session_factory()
    try:
        stock_row = session.query(Stock).filter(Stock.symbol == SYMBOL).first()
        latest_bar_date = None
        if stock_row is not None:
            latest_timestamp = (
                session.query(func.max(PriceBar.timestamp))
                .filter_by(stock_id=stock_row.id, timeframe=Timeframe.ONE_DAY)
                .scalar()
            )
            latest_bar_date = latest_timestamp.date() if latest_timestamp is not None else None
        post_signal_bar_count_before = (
            session.query(func.count(PriceBar.id)).filter_by(stock_id=stock_row.id, timeframe=Timeframe.ONE_DAY).scalar()
            if stock_row is not None
            else 0
        )
    finally:
        session.close()

    today = datetime.now(timezone.utc).date()
    if latest_bar_date is not None:
        date_from = latest_bar_date + timedelta(days=1)
    else:
        date_from = today - timedelta(days=BACKFILL_DAYS)
    date_to = today

    _print("")
    _print("--- Phase A: local DB evidence (zero SAHMK cost) ---")
    _print(f"stock_row_found: {stock_row is not None}")
    _print(f"latest_existing_local_bar_date: {latest_bar_date.isoformat() if latest_bar_date else 'None (no bars)'}")
    _print(f"post_signal_bar_count_before (total ONE_DAY bars on record): {post_signal_bar_count_before}")
    _print(f"computed request_start_date: {date_from.isoformat()}")
    _print(f"computed request_end_date: {date_to.isoformat()}")

    if date_from > date_to:
        _print("")
        _print("Symbol is already fresh (start date is in the future) -- production code would "
               "make ZERO provider requests here (DB-first freshness check). Aborting: making a "
               "provider request in this state would not reproduce real Basirah semantics.")
        _print("REAL_SAHMK_REQUESTS_USED_BY_THIS_MANDATE: 0")
        return 0

    # --- Phase B: quota snapshot before the call (zero SAHMK cost) -----
    rate_limiter = get_default_rate_limiter()
    quota_before = rate_limiter.get_status()
    _print("")
    _print("--- Phase B: local quota snapshot BEFORE the call ---")
    _print(f"requests_used_today_before: {quota_before.get('requests_used_today')}")

    # --- Phase C: exactly one real wire request, hard-guarded ----------
    client = SahmkClient()
    wire_call_count = {"n": 0}
    original_send = client._send

    async def _guarded_send(path, params):
        wire_call_count["n"] += 1
        if wire_call_count["n"] > 1:
            raise _DiagnosticBudgetExceeded(
                f"BLOCKED: a 2nd real wire request was attempted (path={path!r}) -- "
                "this diagnostic's hard one-request budget forbade it. No network I/O occurred "
                "for this blocked attempt."
            )
        return await original_send(path, params)

    client._send = _guarded_send  # instance-level override only; SahmkClient class/file untouched

    _print("")
    _print("--- Phase C: exactly one real SAHMK Historical request ---")
    _print(f"GET /historical/{SYMBOL}/  params: interval=1d, from={date_from.isoformat()}, to={date_to.isoformat()}")

    http_status = None
    sanitized_detail = ""
    exc_str = ""
    exc_type = None
    result_summary = "UNKNOWN"
    bars_returned = None
    retryable_kind = None

    try:
        raw = await client.get_historical(SYMBOL, interval="1d", date_from=date_from, date_to=date_to)
        http_status = 200
        bars = raw.get("data", []) if isinstance(raw, dict) else None
        bars_returned = len(bars) if isinstance(bars, list) else None
        result_summary = "SUCCESS_200"
        _print(f"HTTP_STATUS: 200")
        _print(f"top_level_keys: {sorted(raw.keys()) if isinstance(raw, dict) else type(raw).__name__}")
        _print(f"bars_returned: {bars_returned}")
    except _DiagnosticBudgetExceeded as exc:
        result_summary = "BUDGET_EXCEEDED_BLOCKED"
        exc_str = str(exc)
        exc_type = "_DiagnosticBudgetExceeded (local guard, no network)"
        _print(f"DIAGNOSTIC GUARD TRIPPED: {exc}")
    except SahmkError as exc:
        exc_type = type(exc).__name__
        http_status = getattr(exc, "status_code", None)
        exc_str = str(exc)
        sanitized_detail = exc.sanitized_provider_detail()
        result_summary = exc_type
        _print(f"HTTP_STATUS: {http_status}")
        _print(f"exception_type: {exc_type}")
        _print(f"str(exc): {exc_str}")
        _print(f"sanitized_provider_detail(): {sanitized_detail}")
    except Exception as exc:  # noqa: BLE001 -- must report every possible outcome, never crash silently
        exc_type = type(exc).__name__
        exc_str = str(exc)
        result_summary = f"UNEXPECTED_{exc_type}"
        retryable_kind = getattr(exc, "kind", None)
        _print(f"exception_type: {exc_type}")
        _print(f"str(exc): {exc_str}")
        _print(f"retryable_kind (if applicable): {retryable_kind}")
    finally:
        await client.close()

    _print("")
    _print(f"real_wire_requests_made_by_this_diagnostic: {wire_call_count['n']}")

    # --- Phase D: quota snapshot after the call (zero SAHMK cost) ------
    quota_after = rate_limiter.get_status()
    _print("")
    _print("--- Phase D: local quota snapshot AFTER the call ---")
    _print(f"requests_used_today_after: {quota_after.get('requests_used_today')}")
    _print(f"delta: {quota_after.get('requests_used_today', 0) - quota_before.get('requests_used_today', 0)}")

    # --- Phase E: downstream data state (read-only) ---------------------
    session2 = session_factory()
    try:
        stock_row2 = session2.query(Stock).filter(Stock.symbol == SYMBOL).first()
        post_signal_bar_count_after = (
            session2.query(func.count(PriceBar.id)).filter_by(stock_id=stock_row2.id, timeframe=Timeframe.ONE_DAY).scalar()
            if stock_row2 is not None
            else 0
        )
    finally:
        session2.close()
    _print("")
    _print("--- Phase E: downstream data state (read-only) ---")
    _print(f"post_signal_bar_count_before: {post_signal_bar_count_before}")
    _print(f"post_signal_bar_count_after: {post_signal_bar_count_after}")

    _print("")
    _print("=" * 72)
    _print("FINAL MACHINE-READABLE SUMMARY")
    _print("=" * 72)
    _print(f"RESULT_SUMMARY: {result_summary}")
    _print(f"HTTP_STATUS: {http_status}")
    _print(f"EXCEPTION_TYPE: {exc_type}")
    _print(f"STR_EXC: {exc_str}")
    _print(f"SANITIZED_PROVIDER_DETAIL: {sanitized_detail}")
    _print(f"REAL_WIRE_REQUESTS_MADE: {wire_call_count['n']}")

    return 0


def main() -> int:
    api_key = os.getenv("SAHMK_API_KEY", "")
    if not api_key:
        _print("FATAL: SAHMK_API_KEY is not set. Cannot proceed.")
        return 1
    return asyncio.run(run())


if __name__ == "__main__":
    sys.exit(main())
