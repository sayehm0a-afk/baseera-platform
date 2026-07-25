# SAHMK Integration — Final Engineering Report

**Date:** 2026-07-25
**Branch:** `claude/sahmk-starter-plan-verification-1zj9q4`
**Verdict: the SAHMK provider layer is ready to merge; Basirah as a
whole is not yet ready for frontend integration.** Two different
questions, two different answers — see "Why these are different
questions" below.

## 1. What was asked, and what happened

| # | Task | Outcome |
|---|---|---|
| 1 | Verify the new API key is detected | **Done.** `bool(os.getenv("SAHMK_API_KEY"))` is `True`; format matches `shmk_live_*`. |
| 2 | Authenticate against the live SAHMK API | **Attempted, not completed.** This sandbox's egress proxy rejects every connection to `app.sahmk.sa` at the network-policy layer (`403` from the proxy itself, before reaching SAHMK) — confirmed with both `curl` and the real client code. Not retried or routed around, per this environment's own policy. |
| 3 | Verify Starter-plan access for Quote/Historical/Market Summary/Fundamentals/Dividends/Corporate Actions/other Starter endpoints | **Could not be verified live**, for the same reason as #2. Every endpoint is implemented and unit-tested against mocked responses instead; see the table in `docs/SAHMK_INTEGRATION.md`. |
| 4 | Document exactly which endpoints work | Documented as "implemented, not live-verified this session" — see table below. Nothing is claimed to work live that wasn't actually observed working. |
| 5 | Document which endpoints are unavailable | Documented: no distinct "corporate actions" endpoint exists in any source consulted; `/events/` (news) requires Pro+, above Starter; batch quotes/gainers-losers/analytics/market-depth/symbol-discovery are Starter-accessible per the SDK docs but not implemented (out of the scope actually requested). |
| 6 | Replace remaining synthetic paths with live SAHMK wherever possible | **Done in code.** Both provider families (`IMarketDataProvider` and `IFundamentalDataProvider`) now have a SAHMK implementation with automatic live/synthetic selection. `grep -rl is_synthetic src/` confirms no third synthetic path exists. |
| 7 | Run a complete end-to-end backend verification | **Done.** `main.py` imports cleanly, both provider factories resolve correctly and fall back gracefully, `GET /market-data/status` returns the expected shape for both provider families. |
| 8 | Run all tests | **Done.** 1025 passed, 12 skipped, 0 failed (`tests/unit/market_data/`: 160 of those). |
| 9 | Commit to a new branch | **Done.** `claude/sahmk-starter-plan-verification-1zj9q4`, pushed. |
| 10 | Final engineering report | This document. |

## 2. Why "live-verify Starter access" and "is the backend ready" are different questions

This sandbox's outbound network is governed by an organization egress
proxy. `app.sahmk.sa:443` is not on that proxy's allow-list — every
connection attempt is rejected with a `403` **from the proxy itself**
(confirmed: the error's URL is the proxy's own `127.0.0.1` address, not
`sahmk.sa`). This is a property of *this specific sandboxed session*,
not of the SAHMK account, the new key, the Starter plan, or the code
written against it. The correct, safe response to a `403`/`407` from
this proxy is to report it, not retry or route around it — which is
what happened, twice (once via `curl`, once via the real client code,
both rejected identically).

Because of that, no task in this session's list that requires an
actual HTTP response from `sahmk.sa` — authenticate, verify each
endpoint, confirm the Starter plan actually unlocks what SAHMK's docs
say it should — could be completed with real evidence. Claiming
otherwise would mean fabricating a result. What *can* be reported
honestly:

- The key is present, well-formed, and never exposed (rules 1-5 of the
  request were followed: never printed, never logged, never committed
  — verified by a repo-wide grep of the staged diff and working tree
  before every commit).
- The client and both provider adapters are fully implemented,
  correctly authenticate via `X-API-Key` with no secret-exchange step
  wired incorrectly, correctly honor this environment's proxy (a real
  bug here was caught and fixed in the *prior* milestone, before this
  session), and are exhaustively tested against mocked SAHMK responses
  for every documented success/error case.
- The **auto-selection mechanism is exactly the safety net for this
  situation, by design**: `provider_factory.py` /
  `fundamental_provider_factory.py` probe connectivity before ever
  returning the live provider, and fall back to the synthetic `Dev*`
  provider on any failure — which is what happened, automatically, with
  no manual intervention, both times this session attempted a live
  call. The same code, run somewhere with real network access to
  `sahmk.sa`, will resolve every "not verified this session" row in the
  table below on its own, without a code change.

## 3. Endpoint status (see `docs/SAHMK_INTEGRATION.md` for full detail)

| Category | Implemented | Live-verified this session |
|---|---|---|
| Quote | Yes | No (network-policy blocked) |
| Historical OHLCV | Yes | No |
| Market Summary | Yes | No |
| Company Fundamentals | Yes | No |
| Dividends | Yes | No |
| Company Profile | Yes | No |
| Corporate Actions | No dedicated endpoint exists (mapped to Dividends, disclosed as an inference) | N/A |
| Market news / events | Yes, but requires Pro+ (above Starter) | No |
| Batch quotes, gainers/losers, analytics, market depth, symbol discovery | Not implemented (not requested; documented as future scope) | N/A |

## 4. Is the Basirah backend ready for frontend integration?

**Not yet — for reasons independent of anything done this session.**
Three separate gaps, none of them about SAHMK:

1. **Live SAHMK access is unverified.** Everything above the code
   layer — whether Starter actually returns the documented fields for
   each endpoint, what the real error shape is for an expired/invalid
   key, real rate limits — needs one real run outside this sandbox.
   This is a one-time verification step, not further engineering.
2. **No consumer-facing REST endpoints exist yet.** `main.py` currently
   exposes only health checks and one diagnostic endpoint
   (`GET /market-data/status`, which reports *which provider is
   active*, not stock data). There is no `GET /stocks/{symbol}/quote`,
   `/stocks/{symbol}/history`, or `/stocks/{symbol}/fundamentals` route
   a frontend could call. The provider/service layer this session
   completed is the foundation those routes would sit on, not a
   replacement for them.
3. **Ingestion is not wired into any scheduler.** `ingest_ohlcv.py` and
   `ingest_fundamentals.py` are directly callable functions with no
   caller — no cron job, worker, or task-queue entry invokes them. A
   frontend reading from Basirah's own database (rather than proxying
   live SAHMK calls per-request) would see an empty `price_bars`/
   `fundamental_snapshots` table today. This has been true since M2.1
   and M2.3 respectively and is unchanged by this session's work — it
   is disclosed as pre-existing, not newly discovered.

**What *is* ready:** the data-access layer itself (client → service →
provider → automatic live/synthetic selection) is complete, tested, and
correct for both market data and fundamentals. Building the three items
above is now a matter of wiring already-solid pieces together — new API
routes calling `get_market_data_provider()`/`get_fundamental_data_provider()`,
and a scheduler invoking the two ingestion functions — not further
research or vendor integration work.

## 5. Rule compliance (explicit request)

- **Never printed or exposed the key**: confirmed — every command that
  touched the key redirected it to an env var or truncated it before
  printing (e.g. `k[:10]`), never the full value.
- **No logging of the key**: confirmed — `SahmkClient` sends it only as
  a request header; no code path formats it into a log line.
- **No commit of the key**: confirmed — `git diff --cached` and a
  repo-wide grep for the key's prefix pattern were run before every
  commit this session; both came back clean.
- **Read-only requests only**: confirmed — every `SahmkClient` method is
  a `GET`; there is no write/POST/PATCH/DELETE method anywhere in this
  integration.
- **Respected environment network policy**: confirmed — the one live
  attempt this session went through the governed proxy
  (`trust_env=True`, already fixed in the prior milestone) and, on
  receiving a policy `403`, was reported rather than retried, worked
  around, or bypassed.
