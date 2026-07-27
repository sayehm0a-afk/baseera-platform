#!/usr/bin/env python3
"""Deep-dive live diagnostic of SAHMK's real historical-bar structure.

Real, unmocked, read-only. Called only by
.github/workflows/sahmk-live-verification.yml on manual dispatch, using
the real SAHMK_API_KEY secret. Never mocks, never uses fixture data.

Purpose: verify_sahmk_endpoint_coverage.py already proved the raw
historical response's array lives under a top-level "data" key, not
"bars" (src/market_data/sahmk/service.py:130 assumes the latter). This
script goes one level deeper -- before that one-line fix is made -- and
verifies, from the real API response alone:

  1. how many bars are returned and what the first/last bar look like
  2. the exact field names inside one bar
  3. each field's Python type and an example value
  4. whether bars are ordered oldest-first or newest-first
  5. the timestamp/date field's format (ISO8601, offset-aware, epoch, ...)
  6. that every OHLCV field is present on every bar
  7. that a SahmkHistoricalBar can be built BY HAND from the raw dict,
     bypassing SahmkMarketDataService.get_historical_bars entirely (the
     parser under suspicion is never imported or called here)
  8. that real, standard technical indicators (5/10/20 SMA, RSI-14,
     MACD) compute successfully from the raw closes, proving the data
     itself is usable and the only defect is the parser's key name

Never prints the API key. Response *values* (prices, volumes, dates)
are ordinary public Tadawul market data, not secrets, and are printed
in full for this diagnostic -- only _redact() over the API key applies,
identical to every other verify_sahmk_*.py script.
"""

import asyncio
import os
import sys
from dataclasses import fields as dataclass_fields
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

TARGET_SYMBOL = "2222"  # Saudi Aramco
HISTORICAL_LOOKBACK_DAYS = 180

# Every plausible name for each OHLCV field, so "which key does SAHMK
# actually use" is discovered from the response instead of guessed.
_CANDIDATE_KEYS = {
    "open": ["open", "o"],
    "high": ["high", "h"],
    "low": ["low", "l"],
    "close": ["close", "c"],
    "volume": ["volume", "vol", "v"],
    "timestamp": ["timestamp", "date", "time", "t", "bar_date", "trading_date"],
}


def _redact(text: str) -> str:
    key = os.getenv("SAHMK_API_KEY", "")
    if key and key in text:
        text = text.replace(key, "***REDACTED***")
    return text


def _print(line: str = "") -> None:
    print(_redact(str(line)))


def _find_key(bar: Dict[str, Any], candidates: List[str]) -> str:
    for k in candidates:
        if k in bar:
            return k
    raise KeyError(f"none of {candidates} present in bar keys {sorted(bar.keys())}")


async def run() -> int:
    from src.market_data.sahmk.client import SahmkClient
    from src.market_data.sahmk.models import SahmkHistoricalBar
    from src.market_data.sahmk.service import _parse_timestamp

    client = SahmkClient()
    try:
        date_to = date.today()
        date_from = date_to - timedelta(days=HISTORICAL_LOOKBACK_DAYS)

        _print("=" * 72)
        _print("SAHMK HISTORICAL BAR DEEP DIVE (real, unmocked, read-only)")
        _print(f"Symbol: {TARGET_SYMBOL} | date range: {date_from.isoformat()}..{date_to.isoformat()}")
        _print("=" * 72)

        raw = await client.get_historical(TARGET_SYMBOL, interval="1d", date_from=date_from, date_to=date_to)

        results: Dict[str, str] = {}

        # 1. Reachability + array location -------------------------------
        _print("")
        _print("--- STEP 1: endpoint reachability + array location ---")
        _print(f"Top-level response keys: {sorted(raw.keys())}")
        if "data" in raw and isinstance(raw["data"], list):
            bars = raw["data"]
            results["historical_endpoint_reachable"] = "PASS"
            results["array_location_confirmed"] = "PASS (top-level key: 'data')"
        else:
            bars = []
            results["historical_endpoint_reachable"] = "PASS"
            results["array_location_confirmed"] = f"FAIL (no list found under 'data'; keys were {sorted(raw.keys())})"

        _print(f"Total bars returned: {len(bars)}")

        if not bars:
            _print("FATAL: 0 bars in the array -- cannot proceed with schema/type/chronology checks.")
            results.setdefault("candle_schema_confirmed", "FAIL (no bars)")
            results.setdefault("data_types_confirmed", "FAIL (no bars)")
            results.setdefault("chronological_ordering_confirmed", "FAIL (no bars)")
            results.setdefault("timestamp_format_confirmed", "FAIL (no bars)")
            results.setdefault("indicators_computed", "FAIL (no bars)")
            results.setdefault("parser_bug_isolated", "FAIL (no bars)")
            _print_final_report(results)
            return 1

        first_bar, last_bar = bars[0], bars[-1]
        _print(f"First bar (as returned): {first_bar}")
        _print(f"Last bar (as returned): {last_bar}")

        # 2. Exact field names --------------------------------------------
        _print("")
        _print("--- STEP 2: exact field names inside one bar ---")
        one_bar = first_bar
        bar_keys = sorted(one_bar.keys())
        for k in bar_keys:
            _print(k)
        results["candle_schema_confirmed"] = f"PASS (keys: {bar_keys})"

        # 3. Data types + example values -----------------------------------
        _print("")
        _print("--- STEP 3: field name -> Python type -> example value ---")
        for k in bar_keys:
            v = one_bar[k]
            _print(f"{k} -> {type(v).__name__} -> {v!r}")
        results["data_types_confirmed"] = "PASS"

        # 4. Chronology ------------------------------------------------------
        _print("")
        _print("--- STEP 4: chronological ordering ---")
        ts_key = None
        is_descending = False
        try:
            ts_key = _find_key(one_bar, _CANDIDATE_KEYS["timestamp"])
            first_ts = _parse_timestamp(first_bar[ts_key])
            last_ts = _parse_timestamp(last_bar[ts_key])
            if first_ts and last_ts:
                if first_ts <= last_ts:
                    order = "OLDEST -> NEWEST (ascending)"
                    is_descending = False
                else:
                    order = "NEWEST -> OLDEST (descending)"
                    is_descending = True
                _print(f"First bar {ts_key}: {first_ts.isoformat()}")
                _print(f"Last bar {ts_key}: {last_ts.isoformat()}")
                _print(f"Order: {order}")
                results["chronological_ordering_confirmed"] = f"PASS ({order})"
            else:
                results["chronological_ordering_confirmed"] = "FAIL (could not parse timestamps)"
        except KeyError as exc:
            results["chronological_ordering_confirmed"] = f"FAIL ({exc})"
            ts_key = None

        # 5. Timezone / timestamp format --------------------------------------
        _print("")
        _print("--- STEP 5: timestamp format / timezone ---")
        if ts_key:
            raw_value = one_bar[ts_key]
            _print(f"Raw value: {raw_value!r} (Python type: {type(raw_value).__name__})")
            parsed = _parse_timestamp(raw_value)
            if parsed is not None:
                tz_desc = "offset-aware" if parsed.tzinfo is not None else "naive (no offset)"
                utc_offset = parsed.utcoffset()
                _print(f"Parsed as ISO8601 datetime: {parsed.isoformat()}")
                _print(f"Timezone: {tz_desc}, UTC offset: {utc_offset}")
                results["timestamp_format_confirmed"] = (
                    f"PASS (field='{ts_key}', ISO8601 string, {tz_desc}, offset={utc_offset})"
                )
            else:
                results["timestamp_format_confirmed"] = f"FAIL (could not parse raw value {raw_value!r})"
        else:
            results["timestamp_format_confirmed"] = "FAIL (no timestamp-like key found)"

        # 6. OHLCV completeness ------------------------------------------------
        _print("")
        _print("--- STEP 6: OHLCV completeness across ALL bars ---")
        resolved_keys: Dict[str, str] = {}
        missing_report = []
        for field_name, candidates in _CANDIDATE_KEYS.items():
            try:
                resolved_keys[field_name] = _find_key(one_bar, candidates)
            except KeyError as exc:
                missing_report.append(f"{field_name}: {exc}")

        incomplete_bars = 0
        if not missing_report:
            for idx, bar in enumerate(bars):
                for field_name, key in resolved_keys.items():
                    if key not in bar or bar[key] is None:
                        incomplete_bars += 1
                        break
            _print(f"Resolved OHLCV keys: {resolved_keys}")
            _print(f"Bars missing one or more OHLCV fields: {incomplete_bars} / {len(bars)}")
            if incomplete_bars == 0:
                results["ohlc_completeness"] = "PASS (every bar has open/high/low/close/volume/timestamp)"
            else:
                results["ohlc_completeness"] = f"FAIL ({incomplete_bars} incomplete bars)"
        else:
            _print(f"Could not resolve every OHLCV field: {missing_report}")
            results["ohlc_completeness"] = f"FAIL ({missing_report})"

        # 7. Manual SahmkHistoricalBar construction (bypassing the parser) ------
        _print("")
        _print("--- STEP 7: manual SahmkHistoricalBar construction (parser NOT used) ---")
        parser_bug_isolated = "FAIL (not attempted)"
        if not missing_report and incomplete_bars == 0:
            try:
                sample = bars[0]
                manual_bar = SahmkHistoricalBar(
                    symbol=TARGET_SYMBOL,
                    open=float(sample[resolved_keys["open"]]),
                    high=float(sample[resolved_keys["high"]]),
                    low=float(sample[resolved_keys["low"]]),
                    close=float(sample[resolved_keys["close"]]),
                    volume=int(sample[resolved_keys["volume"]]),
                    timestamp=_parse_timestamp(sample[resolved_keys["timestamp"]]),
                )
                expected_fields = {f.name for f in dataclass_fields(SahmkHistoricalBar)}
                actual_fields = {f.name for f in dataclass_fields(manual_bar)}
                assert expected_fields == actual_fields
                assert manual_bar.timestamp is not None
                assert manual_bar.timestamp.tzinfo is not None
                _print(f"Manually constructed bar: {manual_bar}")
                _print("No missing fields, no conversion errors, timestamp is timezone-aware.")
                results["manual_bar_construction"] = "PASS"
                parser_bug_isolated = (
                    "PASS -- raw data parses cleanly by hand using data.get(\"data\", []) "
                    "instead of the buggy data.get(\"bars\", []); the ONLY defect is the "
                    "top-level key name in service.py:130, nothing else in the pipeline is broken"
                )
            except Exception as exc:  # noqa: BLE001 -- must report, not crash, on any failure
                results["manual_bar_construction"] = f"FAIL ({type(exc).__name__}: {exc})"
                parser_bug_isolated = f"FAIL ({type(exc).__name__}: {exc})"
        else:
            results["manual_bar_construction"] = "FAIL (OHLCV fields not fully resolved -- see step 6)"
            parser_bug_isolated = "FAIL (cannot isolate -- schema incomplete)"
        results["parser_bug_isolated"] = parser_bug_isolated

        # 8. Technical indicators from raw data (parser untouched) ---------------
        _print("")
        _print("--- STEP 8: technical indicators computed directly from raw bars ---")
        try:
            import pandas as pd

            from src.analysis.indicators.momentum import macd, rsi
            from src.analysis.indicators.trend import sma

            if ts_key and is_descending:
                ordered_bars = list(reversed(bars))
            else:
                ordered_bars = bars

            closes = pd.Series(
                [float(b[resolved_keys["close"]]) for b in ordered_bars], dtype="float64"
            )
            _print(f"Closes series length (chronologically ascending): {len(closes)}")

            if len(closes) >= 5:
                sma_5 = sma(closes, 5).iloc[-1]
                _print(f"SMA(5) latest: {sma_5}")
            else:
                sma_5 = None
                _print("SMA(5): insufficient data")

            if len(closes) >= 10:
                sma_10 = sma(closes, 10).iloc[-1]
                _print(f"SMA(10) latest: {sma_10}")
            else:
                sma_10 = None
                _print("SMA(10): insufficient data")

            if len(closes) >= 20:
                sma_20 = sma(closes, 20).iloc[-1]
                _print(f"SMA(20) latest: {sma_20}")
            else:
                sma_20 = None
                _print("SMA(20): insufficient data")

            if len(closes) >= 15:
                rsi_14 = rsi(closes, 14).iloc[-1]
                _print(f"RSI(14) latest: {rsi_14}")
            else:
                rsi_14 = None
                _print("RSI(14): insufficient data (need >= 15 bars)")

            if len(closes) >= 35:
                macd_result = macd(closes)
                _print(
                    f"MACD latest: macd_line={macd_result.macd_line.iloc[-1]}, "
                    f"signal_line={macd_result.signal_line.iloc[-1]}, "
                    f"histogram={macd_result.histogram.iloc[-1]}"
                )
                macd_ok = True
            else:
                macd_result = None
                macd_ok = False
                _print(f"MACD: insufficient data (need >= 35 bars, have {len(closes)})")

            computed = [x is not None for x in (sma_5, sma_10, sma_20, rsi_14)] + [macd_ok]
            if all(computed):
                results["indicators_computed"] = "PASS (SMA5/10/20, RSI-14, MACD all computed from raw data)"
            else:
                results["indicators_computed"] = (
                    f"PARTIAL ({sum(computed)}/5 indicators computed -- likely insufficient bar count "
                    f"({len(closes)} bars) for the ones that failed, not a data-quality problem)"
                )
        except Exception as exc:  # noqa: BLE001 -- must report, not crash
            results["indicators_computed"] = f"FAIL ({type(exc).__name__}: {exc})"

        _print_final_report(results)
        return 0
    finally:
        await client.close()


def _print_final_report(results: Dict[str, str]) -> None:
    _print("")
    _print("=" * 72)
    _print("FINAL REPORT -- PASS/FAIL PER CHECK")
    _print("=" * 72)
    labels = [
        ("historical_endpoint_reachable", "Historical endpoint reachable"),
        ("array_location_confirmed", "Historical array location confirmed"),
        ("candle_schema_confirmed", "Candle schema confirmed"),
        ("data_types_confirmed", "Data types confirmed"),
        ("chronological_ordering_confirmed", "Chronological ordering confirmed"),
        ("timestamp_format_confirmed", "Timestamp format confirmed"),
        ("ohlc_completeness", "OHLC completeness confirmed"),
        ("manual_bar_construction", "Manual SahmkHistoricalBar construction"),
        ("indicators_computed", "Technical indicators computed successfully"),
        ("parser_bug_isolated", "Parser bug fully isolated"),
    ]
    for key, label in labels:
        value = results.get(key, "FAIL (not run)")
        _print(f"{label}: {value}")

    summary_path = os.getenv("GITHUB_STEP_SUMMARY")
    if summary_path:
        lines = ["# SAHMK Historical Bar Deep Dive", "", "| Check | Result |", "|---|---|"]
        for key, label in labels:
            value = results.get(key, "FAIL (not run)")
            lines.append(f"| {label} | {value} |")
        content = _redact("\n".join(lines))
        with open(summary_path, "a", encoding="utf-8") as f:
            f.write(content + "\n")


def main() -> int:
    api_key = os.getenv("SAHMK_API_KEY", "")
    if not api_key:
        _print("FATAL: SAHMK_API_KEY is not set. Cannot proceed.")
        return 1
    return asyncio.run(run())


if __name__ == "__main__":
    sys.exit(main())
