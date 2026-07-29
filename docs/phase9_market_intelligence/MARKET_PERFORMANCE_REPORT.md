# Market Performance Report — Basirah Phase 9

Real, measured performance of the full discovery → ingestion → scan pipeline against the live SAHMK API, run 30444421326.

## Wall-clock timings (from the script's own internal instrumentation, printed verbatim in the log's FINAL SUMMARY)

| Step | Seconds | Minutes |
|---|---|---|
| Discovery (company directory) | 0.80 | 0.01 |
| Historical OHLCV ingestion | 299.62 | 5.00 |
| Fundamentals ingestion | 550.71 | 9.18 |
| Dividends ingestion | 51.17 | 0.85 |
| Full-universe scan (technical + fundamental + AI decision, 95 symbols) | 249.20 | 4.15 |
| **Sum of instrumented steps** | **1,151.50** | **19.19** |

The GitHub Actions job's total wall-clock time was 20m33s (10:37:59Z → 10:58:32Z), consistent with the ~19m11s of instrumented pipeline work plus checkout/dependency-install/DB-migration/pytest overhead.

## Real SAHMK API call accounting

```
Real SAHMK API calls made this run: 400
```

Counted via a rate-limiter call counter that wraps the real, shared `SahmkRateLimiter.acquire()` singleton every `SahmkClient` call goes through — an exact count, not an estimate. This reconciles with the expected 4 calls/symbol × 100 symbols (historical OHLCV + financials + dividends + quote) = 400, confirming no retries, no duplicate calls, and no calls bypassing the shared rate limiter.

## Market session state at scan time

```
Market open at scan time: True
```

Confirms this scan ran against live, current Tadawul session prices — not stale or after-hours data — satisfying the "today's live market session" requirement.

## Artifact retrievability (environment-specific finding, not a Basirah defect)

The full per-company JSON artifact (`market_intelligence_data.json`, 1,466,212 bytes, containing every field including `contributor_breakdown` and full narrative explanations) was uploaded successfully by the workflow via `actions/upload-artifact@v4`. It could **not** be downloaded in this validation session: GitHub's artifact download always redirects to Azure Blob Storage (`*.blob.core.windows.net`), which this sandbox's network policy blocks (confirmed via direct `curl` returning `CONNECT tunnel failed, response 403`, consistent with `/root/.ccr/README.md`'s documented policy). The alternate whole-run-logs ZIP URL (`results-receiver.actions.githubusercontent.com`) was also tested and is also blocked.

**Mitigation applied**: the script was extended (commit `dfbece1`) to print the full condensed company table and every ranking/watchlist category's real entries directly to stdout, which — unlike the artifact — is retrievable via the `get_job_logs` API. All figures, scores, recommendations, targets, and rankings in this report set come from that log-printed data, cross-verified against the script's own summary counters. The only information genuinely inaccessible in this validation session is the full narrative reasoning text and the complete `contributor_breakdown` JSON per company, which exist in the (unretrieved) artifact but are not required for any of the quantitative figures reported here.

## Resource-cleanup gap identified (real, minor)

```
Unclosed client session
Unclosed connector
```

`scripts/verify_sahmk_market_intelligence.py` never calls `market_provider.disconnect()` / `fundamental_provider.disconnect()` at the end of `main()`, leaving an aiohttp session and TCP connector open at process exit. This is a real, minor resource-cleanup gap in the validation script (not in production request-handling code, which has its own lifecycle management) — noted for `DATA_QUALITY_REPORT.md`'s and `READINESS_SCORECARD.md`'s completeness, not yet fixed (fixing it would require another commit+run cycle, out of scope for a report-only deliverable per the "no new runs" constraint).
