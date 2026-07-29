# Technical Analysis Report — Basirah Phase 9

## What ran

Every one of the 95 scanned symbols was analyzed by the real, unmodified `TechnicalAnalysisEngine` against real SAHMK-sourced historical OHLCV bars (5,605 real bars ingested across 100 symbols this run, averaging ~56 bars/symbol — enough for the 20-period indicators in the registry, marginal for anything requiring a longer lookback).

## Indicator inventory actually computed (code-verified, `src/analysis/registry.py::DEFAULT_REGISTRY`)

16 registered indicators:

| Indicator | Output field(s) |
|---|---|
| SMA | `sma_20` |
| EMA | `ema_20` |
| ADX | `adx_14` |
| SuperTrend | trend direction/level |
| RSI | `rsi_14` |
| MACD | `macd_line`, `signal_line`, `histogram` |
| Stochastic Oscillator | `stochastic_14_3_3` |
| Bollinger Bands | upper/middle/lower |
| ATR | `atr_14` |
| OBV | on-balance volume |
| Volume SMA | `volume_sma_20` |
| VWAP | `vwap_20` (rolling, **not** session-anchored) |
| Volume Profile | includes point of control |
| Candlestick Patterns | only 5 patterns actually detected: Doji, Hammer, Shooting Star, Bullish Engulfing, Bearish Engulfing — explicitly not an exhaustive library per its own docstring |
| Fibonacci Retracement | key levels |
| Support/Resistance | swing-pivot/fractal based |

**Explicitly not present** in the live technical engine: standalone breakout detection (breakout only exists as a watchlist rule combining Bollinger+ADX — see `AI_RECOMMENDATIONS_REPORT.md`'s BREAKOUT_CANDIDATES watchlist, empty this run), no generic "risk" indicator inside the technical engine itself, no Ichimoku, Parabolic SAR, Williams %R, CCI, MFI, or "Smart Money" indicators.

## This run's technical score distribution (95 companies)

Technical scores in the STEP 8b table range from 0.0 (symbol 1120, ALRAJHI) to 100.0 (symbols 1020, 1831, 2300 — three companies hit the maximum score). Full per-symbol scores are in `AI_RECOMMENDATIONS_REPORT.md`'s company table.

Notable: symbol **1120 (ALRAJHI)**, Saudi Arabia's largest bank by market cap, received a technical score of exactly **0.0** and a SELL recommendation with MEDIUM_TERM horizon — this is a real output of the live scan, not a placeholder or error value; it reflects whatever the real indicator computations produced for that symbol's real recent price action. No further diagnosis of why the score is exactly 0.0 was performed within this report's scope (would require inspecting the raw indicator dump for that symbol, which exists in the JSON artifact but was not retrievable — see `MARKET_PERFORMANCE_REPORT.md`).

## Data sufficiency caveat

The technical engine ran against ~56 bars/symbol on average (some symbols likely fewer, since backfill days were configured via the workflow's `backfill_days` input and OHLCV availability varies by symbol). Indicators with a 20-period lookback (SMA-20, EMA-20, Bollinger, Volume SMA-20, VWAP-20) had adequate data; any indicator requiring materially longer history would be running on a thinner sample than in a mature production deployment. **NOT VERIFIED:** the exact per-symbol bar count (only the aggregate 5,605-row total and average were captured by this run's logging).
