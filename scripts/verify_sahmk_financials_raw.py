#!/usr/bin/env python3
"""Dumps the REAL, full, nested JSON body of SAHMK's GET
/financials/{symbol}/ response for a small set of symbols.

Phase 1 Fix #3 of the production-readiness pass: `fundamental_score` is
None for every live recommendation because
SahmkMarketDataService.get_financials() only looks for its required
figures (revenue, net_income, total_assets, ...) at the TOP LEVEL of
the response, and SahmkFundamentalDataProvider then rejects the whole
symbol with SahmkResponseValidationError when they're not found there.
Whether they're actually nested one or more levels down (e.g. under
"balance_sheet"/"income_statement"/"cash_flow" keys) has never been
directly observed -- this script exists purely to observe it, so the
parser can be fixed against real evidence instead of another guess at
plausible top-level key names.

Never mocks, never uses fixture data -- a single real, unparsed GET per
symbol. Read-only. Never prints the API key (same _redact() discipline
as verify_sahmk_endpoint_coverage.py).

Usage:
    SAHMK_API_KEY=... python3 scripts/verify_sahmk_financials_raw.py
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

TARGET_SYMBOLS = ["2222", "1120", "2010"]


def _redact(text: str) -> str:
    key = os.getenv("SAHMK_API_KEY", "")
    if key and key in text:
        text = text.replace(key, "***REDACTED***")
    return text


def _print(line: str = "") -> None:
    print(_redact(line))


def _describe_shape(value: Any, depth: int = 0, max_depth: int = 3) -> Any:
    """A structural summary (keys and value types, not full data) so
    nesting is visible even for a large response, without assuming
    anything about what the keys mean."""
    if depth >= max_depth:
        return type(value).__name__
    if isinstance(value, dict):
        return {k: _describe_shape(v, depth + 1, max_depth) for k, v in value.items()}
    if isinstance(value, list):
        if not value:
            return "list[empty]"
        return [f"list[{len(value)}] of ->", _describe_shape(value[0], depth + 1, max_depth)]
    return type(value).__name__


async def run() -> int:
    from src.market_data.sahmk.client import SahmkClient
    from src.market_data.sahmk.exceptions import SahmkError

    client = SahmkClient()
    exit_code = 0
    try:
        for symbol in TARGET_SYMBOLS:
            _print("=" * 72)
            _print(f"GET /financials/{symbol}/ (period=annual) -- RAW, unparsed")
            _print("=" * 72)
            try:
                raw = await client.get_financials(symbol, period_type="annual")
            except SahmkError as exc:
                _print(f"REQUEST FAILED: {type(exc).__name__}: {exc}")
                exit_code = 1
                continue

            _print("")
            _print("-- Structural shape (keys + value types, depth 3) --")
            _print(json.dumps(_describe_shape(raw), indent=2, default=str))
            _print("")
            _print("-- Full raw response body --")
            _print(json.dumps(raw, indent=2, default=str))
            _print("")

        summary_path = os.getenv("GITHUB_STEP_SUMMARY")
        if summary_path:
            with open(summary_path, "a", encoding="utf-8") as f:
                f.write("# SAHMK /financials/ Raw Structure Dump\n\n")
                f.write("See the job log for the full raw response body per symbol.\n")

        return exit_code
    finally:
        await client.close()


def main() -> int:
    if not os.getenv("SAHMK_API_KEY"):
        _print("FATAL: SAHMK_API_KEY is not set. Cannot proceed.")
        return 1
    return asyncio.run(run())


if __name__ == "__main__":
    sys.exit(main())
