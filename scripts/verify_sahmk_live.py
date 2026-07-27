#!/usr/bin/env python3
"""Live, unmocked, end-to-end SAHMK production verification.

Runs four layers, in order, stopping as soon as a layer's outcome
already determines the final diagnosis (see
scripts/sahmk_live_diagnosis.py for the full decision tree):

  A. DNS + TLS reachability to app.sahmk.sa.
  B. A raw HTTP GET https://app.sahmk.sa/api/v1/quote/2222/ with
     X-API-Key, built directly with aiohttp -- no Basirah code
     involved yet. Proves the official API itself is reachable and the
     key is valid, independent of anything this repository built.
  C. The real, production `SahmkClient.get_quote` and
     `SahmkMarketDataService.get_latest_quote` -- no monkeypatching, no
     fixtures, no mocked transport. Proves Basirah's own client reaches
     the real API and parses/normalizes a real response correctly.
  D. Real historical bars (`SahmkMarketDataService.get_historical_bars`)
     fed through the real `TechnicalAnalysisEngine` and
     `RecommendationEngine` -- the actual production analysis pipeline,
     not a stand-in. Proves real market data can complete a real
     analysis result end to end.

SECURITY: SAHMK_API_KEY is read once from the environment and never
printed, logged, written to a file, or included in any exception
message this script constructs itself. `_redact` is applied as
defense-in-depth to every line this script prints, in case a
third-party exception message happens to echo request state. HTTP
request headers are never printed -- only response status/content-type/
timing. Raw response bodies are never printed in full; only a small,
explicit allow-list of extracted fields.

Usage:
    SAHMK_API_KEY=... python3 scripts/verify_sahmk_live.py

Exit code: 0 if a conclusive diagnosis (any of the 8 required values)
was reached, 1 for INCONCLUSIVE or an unhandled error in the script
itself. The exit code says "the diagnostic ran successfully," not "the
verification result was good news" -- SAHMK_KEY_INVALID is exit 0.
"""

import asyncio
import json
import os
import socket
import sys
import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import aiohttp  # noqa: E402

from scripts.sahmk_live_diagnosis import (  # noqa: E402
    DIAGNOSIS_MEANINGS,
    Diagnosis,
    LayerAResult,
    LayerBOutcome,
    LayerCOutcome,
    LayerDOutcome,
    LayerOutcomes,
    determine_final_diagnosis,
)

SAHMK_HOST = "app.sahmk.sa"
TARGET_SYMBOL = "2222"  # Saudi Aramco
DEFAULT_TIMEOUT_SECONDS = float(os.getenv("SAHMK_VERIFY_TIMEOUT_SECONDS", "20"))
HISTORICAL_LOOKBACK_DAYS = 180  # generous window to clear the >=35 trading-day minimum


def _redact(text: str) -> str:
    """Defense-in-depth: strips the literal API key value out of any
    string before it is printed, even though no code path here is
    intended to ever include it. Never a substitute for not printing it
    in the first place."""
    key = os.getenv("SAHMK_API_KEY", "")
    if key and key in text:
        text = text.replace(key, "***REDACTED***")
    return text


def _print(line: str = "") -> None:
    print(_redact(line))


def _sanitize_scalar(value: Any, max_len: int = 80) -> Any:
    """Allow-lists a single extracted field for safe printing: numbers/
    bools pass through, everything else is stringified and truncated.
    Never returns a full nested object -- exactly the
    "don't print the full raw response" requirement, applied per-field."""
    if value is None or isinstance(value, (bool, int, float)):
        return value
    text = str(value)
    return text if len(text) <= max_len else text[: max_len - 3] + "..."


def _first_present(data: Dict[str, Any], keys: List[str]) -> Any:
    for k in keys:
        if k in data and data[k] is not None:
            return data[k]
    return None


# ----------------------------------------------------------------------
# Layer A -- DNS + TLS
# ----------------------------------------------------------------------


@dataclass
class LayerAReport:
    result: LayerAResult
    detail: str
    resolved_address_count: Optional[int] = None


async def check_layer_a(timeout_seconds: float) -> LayerAReport:
    loop = asyncio.get_event_loop()
    try:
        infos = await asyncio.wait_for(
            loop.getaddrinfo(SAHMK_HOST, 443, type=socket.SOCK_STREAM),
            timeout=timeout_seconds,
        )
        resolved = len({info[4][0] for info in infos})
    except asyncio.TimeoutError:
        return LayerAReport(LayerAResult.NETWORK_BLOCKED, f"DNS resolution for {SAHMK_HOST} timed out")
    except socket.gaierror as exc:
        return LayerAReport(LayerAResult.NETWORK_BLOCKED, f"DNS resolution failed: {type(exc).__name__}: {exc}")

    timeout = aiohttp.ClientTimeout(total=timeout_seconds, connect=timeout_seconds)
    try:
        # trust_env=True mirrors SahmkClient's own session construction
        # (src/market_data/sahmk/client.py) -- honors any HTTPS_PROXY
        # this runner is configured with, exactly like production.
        async with aiohttp.ClientSession(trust_env=True, timeout=timeout) as session:
            async with session.get(f"https://{SAHMK_HOST}/", timeout=timeout) as resp:
                await resp.read()
                status = resp.status
        return LayerAReport(
            LayerAResult.OK,
            f"TLS handshake succeeded, HTTP response received (status {status})",
            resolved_address_count=resolved,
        )
    except asyncio.TimeoutError:
        return LayerAReport(LayerAResult.NETWORK_BLOCKED, f"Connection to {SAHMK_HOST} timed out after {timeout_seconds}s")
    except aiohttp.ClientProxyConnectionError as exc:
        return LayerAReport(LayerAResult.NETWORK_BLOCKED, f"Egress proxy rejected the connection: {type(exc).__name__}: {exc}")
    except aiohttp.ClientConnectorCertificateError as exc:
        return LayerAReport(LayerAResult.NETWORK_BLOCKED, f"TLS certificate validation failed: {type(exc).__name__}")
    except aiohttp.ClientError as exc:
        return LayerAReport(LayerAResult.NETWORK_BLOCKED, f"Connection failed: {type(exc).__name__}: {exc}")


# ----------------------------------------------------------------------
# Layer B -- direct, raw HTTP call (no Basirah code)
# ----------------------------------------------------------------------


@dataclass
class LayerBReport:
    outcome: LayerBOutcome
    status_code: Optional[int] = None
    content_type: Optional[str] = None
    latency_ms: Optional[float] = None
    top_level_fields: List[str] = field(default_factory=list)
    symbol: Any = None
    price: Any = None
    updated_at: Any = None
    is_delayed: Any = None
    detail: str = ""


async def check_layer_b(api_key: str, base_url: str, timeout_seconds: float) -> LayerBReport:
    url = f"{base_url}/quote/{TARGET_SYMBOL}/"
    headers = {"X-API-Key": api_key}
    timeout = aiohttp.ClientTimeout(total=timeout_seconds, connect=timeout_seconds)
    start = time.monotonic()

    try:
        async with aiohttp.ClientSession(trust_env=True, timeout=timeout) as session:
            async with session.get(url, headers=headers, timeout=timeout) as resp:
                latency_ms = (time.monotonic() - start) * 1000
                status = resp.status
                content_type = resp.headers.get("Content-Type", "")
                raw_text = await resp.text()
    except asyncio.TimeoutError:
        return LayerBReport(LayerBOutcome.NETWORK_BLOCKED, detail=f"Request to {url} timed out after {timeout_seconds}s")
    except aiohttp.ClientError as exc:
        return LayerBReport(LayerBOutcome.NETWORK_BLOCKED, detail=f"{type(exc).__name__}: {exc}")

    is_json = False
    parsed: Dict[str, Any] = {}
    try:
        candidate = json.loads(raw_text)
        if isinstance(candidate, dict):
            is_json = True
            parsed = candidate
    except (json.JSONDecodeError, ValueError):
        pass

    symbol_val = _first_present(parsed, ["symbol", "code", "ticker"]) if is_json else None
    price_val = _first_present(parsed, ["price", "last_price", "close"]) if is_json else None
    updated_at_val = _first_present(parsed, ["updated_at", "timestamp", "last_updated"]) if is_json else None
    is_delayed_val = _first_present(parsed, ["is_delayed", "delayed"]) if is_json else None
    has_required = is_json and price_val is not None

    from scripts.sahmk_live_diagnosis import classify_layer_b

    outcome = classify_layer_b(
        status_code=status,
        network_error=False,
        is_json=is_json,
        has_required_fields=has_required,
    )

    detail = f"HTTP {status}, content-type={content_type!r}"
    if outcome == LayerBOutcome.CONTRACT_MISMATCH:
        detail += " -- response was not a JSON object with a usable 'price' field"

    return LayerBReport(
        outcome=outcome,
        status_code=status,
        content_type=content_type,
        latency_ms=round(latency_ms, 1),
        top_level_fields=sorted(parsed.keys()) if is_json else [],
        symbol=_sanitize_scalar(symbol_val),
        price=_sanitize_scalar(price_val),
        updated_at=_sanitize_scalar(updated_at_val),
        is_delayed=_sanitize_scalar(is_delayed_val),
        detail=detail,
    )


# ----------------------------------------------------------------------
# Layer C -- the real Basirah SahmkClient + SahmkMarketDataService
# ----------------------------------------------------------------------


@dataclass
class LayerCReport:
    outcome: LayerCOutcome
    method_path: str = ""
    symbol: Any = None
    price: Any = None
    timestamp: Any = None
    detail: str = ""


async def check_layer_c() -> LayerCReport:
    from src.market_data.sahmk.client import SahmkClient
    from src.market_data.sahmk.exceptions import SahmkError
    from src.market_data.sahmk.service import SahmkMarketDataService

    # No arguments -- exactly how production code constructs it
    # (src/market_data/provider_factory.py): reads SAHMK_API_KEY and
    # SAHMK_BASE_URL from the environment itself, nothing special-cased
    # for this script.
    client = SahmkClient()
    try:
        try:
            raw = await client.get_quote(TARGET_SYMBOL)
        except SahmkError as exc:
            return LayerCReport(
                LayerCOutcome.CLIENT_ERROR,
                detail=(
                    f"SahmkClient.get_quote (src/market_data/sahmk/client.py) raised "
                    f"{type(exc).__name__} (status={getattr(exc, 'status_code', None)}) even though "
                    f"the direct raw HTTP call in Layer B succeeded"
                ),
            )
        except Exception as exc:  # noqa: BLE001 -- must classify ANY failure, not just SahmkError
            return LayerCReport(
                LayerCOutcome.CLIENT_ERROR,
                detail=f"SahmkClient.get_quote raised unexpected {type(exc).__name__}: {exc}",
            )

        if "price" not in raw:
            # The raw wrapper itself returned something unusable --
            # this is the client's own contract with the wire, so it
            # counts as the client being broken, not the higher-level
            # parser (SahmkMarketDataService) which hasn't run yet.
            return LayerCReport(
                LayerCOutcome.CLIENT_ERROR,
                detail="SahmkClient.get_quote returned a dict with no 'price' key",
            )

        service = SahmkMarketDataService(client=client)
        try:
            quote = await service.get_latest_quote(TARGET_SYMBOL)
        except Exception as exc:  # noqa: BLE001
            return LayerCReport(
                LayerCOutcome.PARSER_ERROR,
                detail=(
                    f"SahmkMarketDataService.get_latest_quote "
                    f"(src/market_data/sahmk/service.py) raised {type(exc).__name__}: {exc}"
                ),
            )

        return LayerCReport(
            LayerCOutcome.OK,
            method_path="SahmkClient.get_quote -> SahmkMarketDataService.get_latest_quote",
            symbol=quote.symbol,
            price=_sanitize_scalar(quote.price),
            timestamp=quote.timestamp.isoformat(),
            detail="Real SahmkClient + SahmkMarketDataService round-trip succeeded",
        )
    finally:
        await client.close()


# ----------------------------------------------------------------------
# Layer D -- real historical data through the real analysis pipeline
# ----------------------------------------------------------------------


@dataclass
class LayerDReport:
    outcome: LayerDOutcome
    bars_used: Optional[int] = None
    recommendation: Any = None
    confidence: Any = None
    final_score: Any = None
    generated_at: Any = None
    detail: str = ""


async def check_layer_d(latest_price: Optional[float]) -> LayerDReport:
    import pandas as pd

    from src.analysis.recommendation.recommendation_engine import RecommendationEngine
    from src.analysis.recommendation.types import AnalysisContext
    from src.analysis.technical_analysis_engine import TechnicalAnalysisEngine
    from src.market_data.sahmk.client import SahmkClient
    from src.market_data.sahmk.exceptions import SahmkEntitlementError, SahmkError
    from src.market_data.sahmk.service import SahmkMarketDataService

    client = SahmkClient()
    try:
        service = SahmkMarketDataService(client=client)
        date_to = date.today()
        date_from = date_to - timedelta(days=HISTORICAL_LOOKBACK_DAYS)
        try:
            bars = await service.get_historical_bars(TARGET_SYMBOL, date_from, date_to, interval="1d")
        except SahmkEntitlementError:
            return LayerDReport(
                LayerDOutcome.PLAN_RESTRICTED,
                detail=(
                    "GET /historical/{symbol}/ returned 403 -- entitlement limitation on the "
                    "current SAHMK plan, not a program failure (docs/SAHMK_INTEGRATION.md)"
                ),
            )
        except SahmkError as exc:
            if getattr(exc, "status_code", None) is None:
                return LayerDReport(
                    LayerDOutcome.NETWORK_BLOCKED,
                    detail=f"Network error fetching historical bars: {type(exc).__name__}: {exc}",
                )
            return LayerDReport(
                LayerDOutcome.PARSER_ERROR,
                detail=(
                    f"SahmkMarketDataService.get_historical_bars raised {type(exc).__name__} "
                    f"(status={exc.status_code})"
                ),
            )
        except Exception as exc:  # noqa: BLE001
            return LayerDReport(
                LayerDOutcome.PARSER_ERROR,
                detail=f"SahmkMarketDataService.get_historical_bars raised unexpected {type(exc).__name__}: {exc}",
            )

        if len(bars) < 35:
            return LayerDReport(
                LayerDOutcome.PIPELINE_ERROR,
                bars_used=len(bars),
                detail=(
                    f"Only {len(bars)} historical bars returned; "
                    f"TechnicalAnalysisEngine._validate (src/analysis/technical_analysis_engine.py) "
                    f"requires at least 35 rows for the default indicator set (MACD warm-up)"
                ),
            )

        df = pd.DataFrame(
            {
                "open": [b.open for b in bars],
                "high": [b.high for b in bars],
                "low": [b.low for b in bars],
                "close": [b.close for b in bars],
                "volume": [b.volume for b in bars],
            },
            index=[b.timestamp for b in bars],
        )

        try:
            technical_result = TechnicalAnalysisEngine().analyze(df)
        except Exception as exc:  # noqa: BLE001
            return LayerDReport(
                LayerDOutcome.PIPELINE_ERROR,
                bars_used=len(bars),
                detail=(
                    f"TechnicalAnalysisEngine.analyze (src/analysis/technical_analysis_engine.py) "
                    f"raised {type(exc).__name__}: {exc}"
                ),
            )

        context = AnalysisContext(symbol=TARGET_SYMBOL, technical_result=technical_result, latest_price=latest_price)
        try:
            result = RecommendationEngine().generate(context)
        except Exception as exc:  # noqa: BLE001
            return LayerDReport(
                LayerDOutcome.PIPELINE_ERROR,
                bars_used=len(bars),
                detail=(
                    f"RecommendationEngine.generate (src/analysis/recommendation/recommendation_engine.py) "
                    f"raised {type(exc).__name__}: {exc}"
                ),
            )

        if result.symbol != TARGET_SYMBOL:
            return LayerDReport(
                LayerDOutcome.PIPELINE_ERROR,
                bars_used=len(bars),
                detail=f"Pipeline result symbol '{result.symbol}' does not match requested '{TARGET_SYMBOL}'",
            )

        return LayerDReport(
            LayerDOutcome.OK,
            bars_used=len(bars),
            recommendation=result.recommendation.value,
            confidence=result.confidence,
            final_score=result.final_score,
            generated_at=result.generated_at.isoformat(),
            detail="Real historical data -> TechnicalAnalysisEngine -> RecommendationEngine succeeded",
        )
    finally:
        await client.close()


# ----------------------------------------------------------------------
# Orchestration
# ----------------------------------------------------------------------


async def run() -> Diagnosis:
    _print("=" * 72)
    _print("SAHMK LIVE PRODUCTION VERIFICATION")
    _print(f"Target symbol: {TARGET_SYMBOL} (Saudi Aramco)")
    _print("=" * 72)

    api_key = os.getenv("SAHMK_API_KEY", "")
    if not api_key:
        _print("FATAL: SAHMK_API_KEY is not set in the environment. Cannot proceed.")
        _print(f"FINAL_DIAGNOSIS={Diagnosis.INCONCLUSIVE.value}")
        return Diagnosis.INCONCLUSIVE
    base_url = os.getenv("SAHMK_BASE_URL", "https://app.sahmk.sa/api/v1").rstrip("/")

    _print("")
    _print("--- LAYER A: DNS + TLS connectivity ---")
    layer_a = await check_layer_a(DEFAULT_TIMEOUT_SECONDS)
    _print(f"Result: {layer_a.result.value}")
    _print(f"Detail: {layer_a.detail}")
    if layer_a.resolved_address_count is not None:
        _print(f"Resolved address count: {layer_a.resolved_address_count}")

    layer_b = LayerBReport(outcome=LayerBOutcome.NETWORK_BLOCKED)
    layer_c = LayerCReport(outcome=LayerCOutcome.NOT_RUN)
    layer_d = LayerDReport(outcome=LayerDOutcome.NOT_RUN)

    if layer_a.result == LayerAResult.OK:
        _print("")
        _print("--- LAYER B: direct raw API call (GET /quote/2222/) ---")
        layer_b = await check_layer_b(api_key, base_url, DEFAULT_TIMEOUT_SECONDS)
        _print(f"Outcome: {layer_b.outcome.value}")
        _print(f"Detail: {layer_b.detail}")
        if layer_b.status_code is not None:
            _print(f"HTTP status: {layer_b.status_code}")
            _print(f"Latency: {layer_b.latency_ms} ms")
            _print(f"Top-level JSON fields: {layer_b.top_level_fields}")
            _print(f"symbol: {layer_b.symbol}")
            _print(f"price: {layer_b.price}")
            _print(f"updated_at: {layer_b.updated_at}")
            _print(f"is_delayed: {layer_b.is_delayed}")

        if layer_b.outcome == LayerBOutcome.OK:
            _print("")
            _print("--- LAYER C: real Basirah SahmkClient + SahmkMarketDataService ---")
            layer_c = await check_layer_c()
            _print(f"Outcome: {layer_c.outcome.value}")
            _print(f"Detail: {layer_c.detail}")
            if layer_c.method_path:
                _print(f"Execution path: {layer_c.method_path}")
            if layer_c.outcome == LayerCOutcome.OK:
                _print(f"Parsed symbol: {layer_c.symbol}")
                _print(f"Parsed price: {layer_c.price}")
                _print(f"Parsed timestamp: {layer_c.timestamp}")

                _print("")
                _print("--- LAYER D: real historical data -> technical engine -> recommendation engine ---")
                layer_d = await check_layer_d(layer_c.price if isinstance(layer_c.price, (int, float)) else None)
                _print(f"Outcome: {layer_d.outcome.value}")
                _print(f"Detail: {layer_d.detail}")
                if layer_d.bars_used is not None:
                    _print(f"Historical bars used: {layer_d.bars_used}")
                if layer_d.outcome == LayerDOutcome.OK:
                    _print(f"Recommendation: {layer_d.recommendation}")
                    _print(f"Confidence: {layer_d.confidence}")
                    _print(f"Final score: {layer_d.final_score}")
                    _print(f"Generated at: {layer_d.generated_at}")

    outcomes = LayerOutcomes(
        layer_a=layer_a.result,
        layer_b=layer_b.outcome,
        layer_c=layer_c.outcome,
        layer_d=layer_d.outcome,
    )
    diagnosis = determine_final_diagnosis(outcomes)

    _print("")
    _print("=" * 72)
    _print("FINAL RESULT MATRIX")
    _print("=" * 72)
    for d in Diagnosis:
        marker = ">>> " if d == diagnosis else "    "
        _print(f"{marker}{d.value}: {DIAGNOSIS_MEANINGS[d]}")
    _print("")
    _print(f"FINAL_DIAGNOSIS={diagnosis.value}")

    summary_path = os.getenv("GITHUB_STEP_SUMMARY")
    if summary_path:
        _write_step_summary(summary_path, layer_a, layer_b, layer_c, layer_d, diagnosis)

    return diagnosis


def _write_step_summary(
    path: str,
    layer_a: LayerAReport,
    layer_b: LayerBReport,
    layer_c: LayerCReport,
    layer_d: LayerDReport,
    diagnosis: Diagnosis,
) -> None:
    icon = "✅" if diagnosis == Diagnosis.FULL_END_TO_END_SUCCESS else (
        "🟢" if diagnosis == Diagnosis.SAHMK_CONNECTION_CONFIRMED else
        "🟡" if diagnosis == Diagnosis.SAHMK_PLAN_RESTRICTION else
        "🔴"
    )
    lines = [
        "# SAHMK Live Verification -- Final Result",
        "",
        f"## {icon} `{diagnosis.value}`",
        "",
        _redact(DIAGNOSIS_MEANINGS[diagnosis]),
        "",
        "## Layer results",
        "",
        "| Layer | Outcome | Detail |",
        "|---|---|---|",
        f"| A -- DNS/TLS | `{layer_a.result.value}` | {_redact(layer_a.detail)} |",
        f"| B -- raw API call | `{layer_b.outcome.value}` | {_redact(layer_b.detail)} |",
        f"| C -- Basirah client/parser | `{layer_c.outcome.value}` | {_redact(layer_c.detail)} |",
        f"| D -- analysis pipeline | `{layer_d.outcome.value}` | {_redact(layer_d.detail)} |",
        "",
    ]
    if layer_b.status_code is not None:
        lines += [
            "## Layer B raw response facts",
            "",
            f"- HTTP status: `{layer_b.status_code}`",
            f"- Latency: `{layer_b.latency_ms} ms`",
            f"- Top-level JSON fields: `{layer_b.top_level_fields}`",
            f"- symbol: `{layer_b.symbol}` / price: `{layer_b.price}` / "
            f"updated_at: `{layer_b.updated_at}` / is_delayed: `{layer_b.is_delayed}`",
            "",
        ]
    if layer_d.outcome == LayerDOutcome.OK:
        lines += [
            "## Layer D pipeline result",
            "",
            f"- Historical bars used: `{layer_d.bars_used}`",
            f"- Recommendation: `{layer_d.recommendation}`",
            f"- Confidence: `{layer_d.confidence}`",
            f"- Final score: `{layer_d.final_score}`",
            f"- Generated at: `{layer_d.generated_at}`",
            "",
        ]
    content = _redact("\n".join(lines))
    with open(path, "a", encoding="utf-8") as f:
        f.write(content + "\n")


def main() -> int:
    diagnosis = asyncio.run(run())
    return 0 if diagnosis != Diagnosis.INCONCLUSIVE else 1


if __name__ == "__main__":
    sys.exit(main())
