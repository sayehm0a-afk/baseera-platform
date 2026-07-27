#!/usr/bin/env python3
"""Comprehensive, real, unmocked SAHMK endpoint coverage check.

Complements scripts/verify_sahmk_live.py's four-layer quote/historical/
pipeline verification (Layers A-D) with the remaining SahmkClient
methods this integration wraps, so a single live run can answer, for
every endpoint Basirah's client implements: does the current
SAHMK_API_KEY and plan actually permit this call, right now, against
production -- not a guess from documentation, a real HTTP response.

Never mocks, never uses fixture data. Read-only: every method called
here is a GET. Never prints the API key or request headers -- only
response status/latency/field names, exactly like verify_sahmk_live.py
(see that script's module docstring for the redaction discipline,
reused here unchanged via the same _redact()).

Also directly diagnoses verify_sahmk_live.py's Layer D finding of "0
historical bars returned": that layer goes through
SahmkMarketDataService.get_historical_bars, which assumes the raw
response has a top-level "bars" key (src/market_data/sahmk/
service.py:130, `data.get("bars", [])`) -- an assumption
docs/SAHMK_INTEGRATION.md itself flags as unverified. This script also
calls SahmkClient.get_historical directly (the raw, unparsed layer)
and prints every top-level key the real response actually has, so
"genuinely no data for this range" can be told apart from "the parser
is looking for the wrong key.".

Usage:
    SAHMK_API_KEY=... python3 scripts/verify_sahmk_endpoint_coverage.py
"""

import asyncio
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

TARGET_SYMBOL = "2222"  # Saudi Aramco


def _redact(text: str) -> str:
    key = os.getenv("SAHMK_API_KEY", "")
    if key and key in text:
        text = text.replace(key, "***REDACTED***")
    return text


def _print(line: str = "") -> None:
    print(_redact(line))


def _sanitize(value: Any, max_len: int = 90) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    text = str(value)
    return text if len(text) <= max_len else text[: max_len - 3] + "..."


@dataclass
class EndpointResult:
    name: str
    method: str
    outcome: str  # OK | AUTH_ERROR | ENTITLEMENT_ERROR | RATE_LIMITED | REQUEST_ERROR | UNEXPECTED_ERROR
    status_code: Optional[int] = None
    latency_ms: Optional[float] = None
    top_level_fields: List[str] = field(default_factory=list)
    sample: Dict[str, Any] = field(default_factory=dict)
    detail: str = ""


async def _call(name: str, method: str, coro) -> EndpointResult:
    from src.market_data.sahmk.exceptions import (
        SahmkAuthenticationError,
        SahmkEntitlementError,
        SahmkRateLimitError,
        SahmkRequestError,
    )

    start = time.monotonic()
    try:
        raw = await coro
        latency = (time.monotonic() - start) * 1000
        top_level = sorted(raw.keys()) if isinstance(raw, dict) else []
        return EndpointResult(
            name=name,
            method=method,
            outcome="OK",
            status_code=200,
            latency_ms=round(latency, 1),
            top_level_fields=top_level,
        )
    except SahmkAuthenticationError as exc:
        latency = (time.monotonic() - start) * 1000
        return EndpointResult(name, method, "AUTH_ERROR", getattr(exc, "status_code", 401), round(latency, 1), detail=str(exc)[:200])
    except SahmkEntitlementError as exc:
        latency = (time.monotonic() - start) * 1000
        return EndpointResult(name, method, "ENTITLEMENT_ERROR", getattr(exc, "status_code", 403), round(latency, 1), detail=str(exc)[:200])
    except SahmkRateLimitError as exc:
        latency = (time.monotonic() - start) * 1000
        return EndpointResult(name, method, "RATE_LIMITED", getattr(exc, "status_code", 429), round(latency, 1), detail=str(exc)[:200])
    except SahmkRequestError as exc:
        latency = (time.monotonic() - start) * 1000
        return EndpointResult(name, method, "REQUEST_ERROR", getattr(exc, "status_code", None), round(latency, 1), detail=str(exc)[:200])
    except Exception as exc:  # noqa: BLE001 -- must classify ANY failure
        latency = (time.monotonic() - start) * 1000
        return EndpointResult(name, method, "UNEXPECTED_ERROR", None, round(latency, 1), detail=f"{type(exc).__name__}: {exc}"[:200])


async def run() -> List[EndpointResult]:
    from src.market_data.sahmk.client import SahmkClient

    client = SahmkClient()
    results: List[EndpointResult] = []
    try:
        date_to = date.today()
        date_from = date_to - timedelta(days=180)

        _print("=" * 72)
        _print("SAHMK ENDPOINT COVERAGE -- full client method sweep (real, read-only)")
        _print(f"Symbol: {TARGET_SYMBOL} | date range: {date_from.isoformat()}..{date_to.isoformat()}")
        _print("=" * 72)

        checks = [
            ("Market summary (index)", "get_market_summary", client.get_market_summary(index="TASI")),
            ("Company profile", "get_company_profile", client.get_company_profile(TARGET_SYMBOL)),
            ("Company directory (symbol lookup)", "get_companies", client.get_companies()),
            ("Financials (fundamentals)", "get_financials", client.get_financials(TARGET_SYMBOL, period_type="annual")),
            ("Dividends", "get_dividends", client.get_dividends(TARGET_SYMBOL)),
        ]

        for name, method, coro in checks:
            result = await _call(name, method, coro)
            results.append(result)
            _print("")
            _print(f"--- {name} ({method}) ---")
            _print(f"Outcome: {result.outcome}")
            if result.status_code is not None:
                _print(f"Status code: {result.status_code}")
            _print(f"Latency: {result.latency_ms} ms")
            if result.top_level_fields:
                _print(f"Top-level fields: {result.top_level_fields}")
            if result.detail:
                _print(f"Detail: {_redact(result.detail)}")

        # Raw (unparsed) historical call -- diagnoses verify_sahmk_live.py's
        # "0 historical bars" finding directly, bypassing
        # SahmkMarketDataService's "bars" key assumption entirely.
        _print("")
        _print("--- Historical (raw, unparsed client.get_historical) ---")
        hist_result = await _call(
            "Historical (raw)",
            "get_historical",
            client.get_historical(TARGET_SYMBOL, interval="1d", date_from=date_from, date_to=date_to),
        )
        results.append(hist_result)
        _print(f"Outcome: {hist_result.outcome}")
        if hist_result.status_code is not None:
            _print(f"Status code: {hist_result.status_code}")
        _print(f"Latency: {hist_result.latency_ms} ms")
        if hist_result.top_level_fields:
            _print(f"Top-level fields in raw response: {hist_result.top_level_fields}")
        if hist_result.detail:
            _print(f"Detail: {_redact(hist_result.detail)}")

        # Rate-limit probe: several rapid sequential quote calls (well
        # within the documented Starter-plan default of 20/min --
        # src/market_data/config.py's SAHMK_MAX_REQUESTS_PER_MINUTE) to
        # observe real throttling behavior without abusing the API.
        _print("")
        _print("--- Rate-limit probe: 5 rapid sequential get_quote calls ---")
        rate_results = []
        for i in range(5):
            r = await _call(f"get_quote burst #{i + 1}", "get_quote", client.get_quote(TARGET_SYMBOL))
            rate_results.append(r)
            _print(f"  call {i + 1}: outcome={r.outcome} status={r.status_code} latency={r.latency_ms}ms")
        results.extend(rate_results)

        _print("")
        _print("=" * 72)
        _print("SUMMARY")
        _print("=" * 72)
        for r in results:
            _print(f"{r.name:40s} outcome={r.outcome:20s} status={str(r.status_code):5s} latency={r.latency_ms}ms")

        summary_path = os.getenv("GITHUB_STEP_SUMMARY")
        if summary_path:
            _write_step_summary(summary_path, results, hist_result)

        return results
    finally:
        await client.close()


def _write_step_summary(path: str, results: List[EndpointResult], hist_result: EndpointResult) -> None:
    lines = [
        "# SAHMK Endpoint Coverage -- Full Sweep",
        "",
        "| Endpoint | Method | Outcome | Status | Latency (ms) | Top-level fields |",
        "|---|---|---|---|---|---|",
    ]
    for r in results:
        fields_str = ", ".join(r.top_level_fields) if r.top_level_fields else "-"
        lines.append(
            f"| {r.name} | `{r.method}` | `{r.outcome}` | {r.status_code} | {r.latency_ms} | {fields_str} |"
        )
    lines += [
        "",
        "## Raw historical response diagnosis",
        "",
        f"Top-level keys in the real, unparsed `/historical/{TARGET_SYMBOL}/` response: "
        f"`{hist_result.top_level_fields}`",
        "",
        "`SahmkMarketDataService.get_historical_bars` (src/market_data/sahmk/service.py:130) "
        'reads `data.get("bars", [])` -- compare against the key list above to see whether '
        "that assumption matches the real API.",
    ]
    content = _redact("\n".join(lines))
    with open(path, "a", encoding="utf-8") as f:
        f.write(content + "\n")


def main() -> int:
    api_key = os.getenv("SAHMK_API_KEY", "")
    if not api_key:
        _print("FATAL: SAHMK_API_KEY is not set. Cannot proceed.")
        return 1
    asyncio.run(run())
    return 0


if __name__ == "__main__":
    sys.exit(main())
