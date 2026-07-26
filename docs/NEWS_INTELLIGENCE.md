# Real News Intelligence Engine

This document describes the News Intelligence Engine: how news is
collected, deduplicated, classified, scored, and fed into the existing
AI Decision Engine and Portfolio Intelligence layer without a second,
parallel recommendation path — its REST API, its operational limits,
and — explicitly — what has and has not been verified.

No claim in this document should be read as "production ready," "fully
complete," or "100% accurate." No sentiment/classification/impact value
produced anywhere in this codebase's tests is a claim about real market
behavior — see §6, "What was live-verified vs. mock-tested."

## 1. Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│ REST layer (src/api/routes/news.py, portfolio.py)                 │
│ GET routes read persisted state; POST /refresh and                │
│ POST .../news-alerts/refresh run synchronously (bounded, small)   │
└───────────────┬───────────────────────────────┬────────────────────┘
                │                               │
                ▼                               ▼
┌───────────────────────────────┐   ┌────────────────────────────────┐
│ NewsIntelligenceService.refresh │   │ PortfolioNewsAlertEngine       │
│ collect → dedup → analyze →     │   │ .generate_and_persist()        │
│ persist                          │   │ classify_alert_type() per held │
└───────────────┬───────────────────┘   symbol's analyzed events      │
                │                    └────────────────┬─────────────────┘
                ▼                                     ▼
┌────────────────────────┐   ┌────────────────────────┐   ┌───────────┐
│ NewsCollector            │   │ NewsAnalyzer (LLM)      │   │ Notification│
│ (wraps IMarketDataProvider│   │ entity/category/        │   │ (PORTFOLIO_ │
│  .get_market_news(),      │   │ sentiment/impact via     │   │  ALERT)     │
│  TTLCache-deduped)         │   │ OpenAILLMClient          │   └───────────┘
└────────────────────────┘   └────────────────────────┘
                │                                     │
                ▼                                     ▼
┌────────────────────────┐   ┌────────────────────────────────────────┐
│ deduplication.py         │   │ NewsEvent / NewsEntity /                │
│ (difflib similarity,      │   │ NewsSourceReliability / PortfolioNewsAlert│
│  external_key idempotency)│   │ (Postgres, via Alembic migration)        │
└────────────────────────┘   └────────────────────────────────────────┘
                                                     │ read by
                                                     ▼
┌──────────────────────────────────────────────────────────────────┐
│ context_builder.build_analysis_context()                         │
│  → NewsIntelligenceService.get_symbol_sentiment() (pure DB read)   │
│  → context.extra["news_sentiment"] = {sentiment_score,             │
│     article_count, events: [...]}                                   │
└───────────────┬──────────────────────────────────────────────────┘
                │ the ONE shared hook point, unchanged since Phase 7
                ▼
┌──────────────────────────────────────────────────────────────────┐
│ AIDecisionEngine → NewsSentimentScoreContributor (pre-existing,     │
│ blended-score formula unchanged; now emits one Signal per event)     │
└──────────────────────────────────────────────────────────────────┘
```

### What was reused unmodified

- `IMarketDataProvider.get_market_news(limit)` — already an existing
  abstract interface method, already implemented for real by
  `SahmkMarketDataProvider` (wraps SAHMK's `/events/` endpoint) and
  honestly-labeled-synthetic by `DevMarketDataProvider`. No new provider
  abstraction was built — the news vendor problem was already solved by
  a prior milestone; this milestone is the first to actually consume it.
- `OpenAILLMClient` (`src/core/llm_abstraction/`) — a real, pre-existing
  OpenAI client, reused as the entity/classification/sentiment/impact
  engine. `NewsAnalyzer` type-hints against `BaseLLMClient` for
  injectability, and constructs `OpenAILLMClient` only when no client is
  explicitly injected.
- `AIRequest`/`record_ai_request()` (Phase 10, `src/analysis/ai_request_recorder.py`)
  — used for real, for the first time, to record every LLM call this
  engine makes (`feature="news_intelligence:analyze"`), including
  failures.
- `NewsSentimentScoreContributor` (`src/analysis/decision/contributors/
  external_factor_contributors.py`) — already existed, already read
  `context.extra["news_sentiment"]`. Its blended `score`/`confidence`
  formula was **not** changed; only its signal-emission was extended
  (§4).
- `build_analysis_context()` — the single function all four consumers
  (`/recommendation`, `/decision`, `/analyst-report`, portfolio holding
  analysis, market scan) already call. Zero changes were needed at any
  of those four call sites.
- `TTLCache` (`src/market_data/caching/ttl_cache.py`), `Notification`
  (`PORTFOLIO_ALERT` type already existed), `AlertSeverity`
  (`src/domain/models/market_alert.py`, reused not redefined),
  `require_staff_role`, the `_get_portfolio_or_404` ownership pattern.

### What was newly built

- Four domain models + migration `6a9ccaf29e1f`: `NewsEvent`,
  `NewsEntity`, `NewsSourceReliability`, `PortfolioNewsAlert`.
- `src/news_intelligence/` (new package): `types.py`, `config.py`,
  `collection.py`, `deduplication.py`, `prompts.py`, `analyzer.py`,
  `source_reliability.py`, `service.py`, `portfolio_alerts.py`.
- `src/api/routes/news.py`, `src/api/schemas/news.py`, two new routes
  on `src/api/routes/portfolio.py`.
- A small, additive extension to `NewsSentimentScoreContributor` (§4)
  and to `build_analysis_context()` (§4) — both backward compatible.

## 2. Collection, deduplication, and idempotency

`NewsCollector.collect(limit)` wraps `IMarketDataProvider.get_market_news()`
in `TTLCache.get_or_compute()` (`NEWS_FETCH_CACHE_TTL_SECONDS`, default
300s) — repeated calls within the TTL window never re-hit the provider,
and concurrent in-flight calls are deduplicated via the cache's existing
`asyncio.Task` tracking (requirement 11: "avoid unnecessary API calls").

Each collected item is checked against two independent, structural
mechanisms — neither is "best effort":

1. **`external_key`** — `sha256(source, normalized_headline,
   published_at)`. A `NewsEvent.external_key` unique constraint makes
   re-ingesting the same article a no-op: it is never re-persisted and
   never re-sent to the LLM (requirement 11: "no duplicated
   processing"). Counted in `RefreshSummary.already_ingested`.
2. **Similarity-based dedup** (`deduplication.find_duplicate`) — for
   items that aren't an exact re-ingestion (a different source
   syndicating the same story, or a lightly-edited republish),
   `difflib.SequenceMatcher` compares the normalized headline against
   canonical events published within `NEWS_DEDUP_LOOKBACK_HOURS`
   (default 72h). A ratio ≥ `NEWS_DEDUP_SIMILARITY_THRESHOLD` (default
   0.85) marks it a duplicate: persisted with `duplicate_of_id` pointing
   at the canonical event, the canonical's `duplicate_count`
   incremented, and — critically — **never independently analyzed**
   (`category`/`sentiment_score`/etc. stay `NULL`). This is the
   mechanism behind requirement 6: "duplicate or recycled news must not
   increase confidence." `SourceReliabilityService.record_article_seen()`
   is likewise called only for the canonical article, never a duplicate.

## 3. Entity recognition, classification, sentiment, and impact

All four (requirements 2-5) come from **one** LLM call per canonical
article (`NewsAnalyzer.analyze()`), not four separate passes — cheaper
and internally consistent, since the entities identified and the
sentiment expressed about them come from the same read of the same
article. The prompt (`prompts.py`) enumerates every category, sentiment
label, and entity type from this milestone's requirements exactly (20
categories, 5 sentiment labels, 4 entity types including
multi-company/government/market-wide) and instructs a single JSON
object response with entities, category, sentiment_score, sentiment_label,
confidence, explanation, and short/medium/long-term + price/risk/
volatility impact fields.

**Never fabricates on failure.** `NewsAnalyzer.analyze()` returns `None`
for: no API key configured, a network/API exception, malformed JSON, or
a non-object JSON response — logged and recorded as a `FAILED`
`AIRequest`, never a fake classification. The corresponding `NewsEvent`
row is persisted with `analyzed_at=None` and every analysis field
`NULL` — an honest "collected but not yet analyzed" state, the same
disclosed-degradation pattern this codebase already uses for
`DevMarketDataProvider` when `SAHMK_API_KEY` is unset. Unknown
category/sentiment_label/entity_type strings returned by the model are
coerced to `OTHER`/`NEUTRAL`/skipped rather than raising — a
resilience measure against minor prompt-format drift, not a silent
data-quality compromise (still recorded as `SUCCESS`, since the rest of
the response was usable).

All numeric fields (`sentiment_score`, `confidence`, impact scores) are
clamped to their documented ranges before persistence, regardless of
what the model returns.

## 4. Decision Engine integration (requirements 8-9) — the core design decision

The spec is explicit: *"Do not create a separate recommendation engine.
Use the existing architecture."* This is met by hooking into
`context_builder.build_analysis_context()` — the one function all four
production consumers (`stocks.py`'s `/recommendation`, `/decision`,
`/analyst-report`; `portfolio_engine.py`'s per-holding analysis;
`scanner.py`'s market scan) already call, unmodified since Phase 7:

```python
def _news_sentiment_extra(session, symbol, news_service) -> Dict[str, Any]:
    try:
        sentiment = news_service.get_symbol_sentiment(session, symbol)
    except Exception:
        log.warning(...)
        return {}
    if sentiment is None:
        return {}
    return {"news_sentiment": {
        "sentiment_score": sentiment.sentiment_score,
        "article_count": sentiment.article_count,
        "events": [...],
    }}
```

`AnalysisContext.extra` — previously always `{}` — now carries this
whenever real analyzed news exists for the symbol. **Zero changes** to
`stocks.py`, `portfolio_engine.py`, or `scanner.py` were needed; the
moment a symbol has fresh analyzed news, the very next call to any of
those four routes reflects it (requirement 8: "the recommendation must
automatically change when important news appears").

`get_symbol_sentiment()` is a **pure, synchronous DB read** — it never
touches the network or the LLM. This matters because it runs on every
single `build_analysis_context()` call across all four consumers;
keeping news scoring off the hot path's critical latency (LLM calls
only happen during `POST /news/refresh`, a separate, explicitly
triggered operation) is what makes requirement 11 ("support continuous
monitoring... avoid unnecessary API calls") true in practice, not just
in the cache layer.

**Weighted aggregation formula** (`get_symbol_sentiment`):
`weight_i = (confidence_i / 100) * source_reliability_score_i`;
`aggregate = clamp(Σ(sentiment_i * weight_i) / Σ(weight_i), -1, 1)`.
A high-confidence article from a reliable source dominates a
low-confidence article from an unreliable one — this is where
requirement 6 ("low-quality sources must have less influence") actually
takes effect on the blended number the decision engine sees, distinct
from the dedup mechanism in §2 (which only prevents *duplicate*
inflation).

**`NewsSentimentScoreContributor`'s blended `score`/`confidence` math
was not changed** — `points = round(sentiment_score * 20, 1)`,
`score = clamp(50 + points, 0, 100)`,
`confidence = clamp(article_count * 20, 0, 100)`, exactly as before this
milestone. What changed is **signal emission** (requirement 9,
explainability): when `context.extra["news_sentiment"]["events"]` is
present and non-empty, the contributor emits one `Signal` per event
(e.g. `"Earnings news (+8.0 pts): Saudi Aramco reports record quarterly
profit"`) instead of a single aggregate signal. These per-event signals
flow through `AIDecisionEngine`'s **already-existing** "top signals
across all contributors, sorted by \|impact\|" explanation-building
logic — zero changes to `ai_decision_engine.py` itself were needed. This
is the mechanism behind the example the spec gave: *"Confidence
increased because: Positive earnings (+8), Government project (+5), RSI
confirmation (+4)"* — the RSI signal already existed from the technical
contributor; the news signals are now genuinely present alongside it,
not fabricated.

### Disclosed scope boundary

`get_symbol_sentiment()` only aggregates `NewsEntityType.COMPANY`
entities matching the exact symbol. Market-wide and government-policy
events (e.g. an interest-rate change, a general Tadawul regulation) are
**not yet blended into individual symbols' decision-engine sentiment** —
they're real, persisted, and queryable via `GET /api/v1/news/market`,
but a market-wide event about "the energy sector" does not currently
move `2222`'s `NewsSentimentScoreContributor` score unless an article
also explicitly names Aramco as a `COMPANY` entity. This is a
deliberate scope boundary for this milestone, not an oversight — see §7.

## 5. Source reliability and portfolio alerts (requirements 6, 10)

`SourceReliabilityService` tracks a `[0, 1]` reliability score per named
source (`NewsSourceReliability`, default 0.5 for an unseen source —
neutral, not automatically trusted). `record_article_seen()` increments
`articles_seen` **only for canonical articles** (§2); `set_reliability()`
is a manual override for staff to curate known-good/known-bad sources
over time (this milestone does not attempt automated reliability
scoring from outcome data — that would require the kind of backtested,
significance-tested calibration `docs/BACKTESTING_AND_CALIBRATION.md`
§5b already builds for the *contributor* weights, and is flagged as
natural follow-up work, not built here).

`PortfolioNewsAlertEngine.generate_and_persist(session, portfolio,
symbols, since=None)` re-evaluates each held symbol's analyzed,
canonical news events (requirement 10) via a pure classification
function:

```
classify_alert_type(category, sentiment_score, confidence):
    if confidence < NEWS_ALERT_MIN_CONFIDENCE (55.0): return None
    if category in {LAWSUIT, BANKRUPTCY, TRADING_SUSPENSION,
                     REGULATORY_CHANGE} or sentiment_score <= -0.5:
        return HIGH_RISK
    if sentiment_score >= 0.6:  return MAJOR_OPPORTUNITY
    if sentiment_score >= 0.2:  return UPGRADE
    if sentiment_score <= -0.2: return DOWNGRADE
    return None
```

A confidence floor gates every branch — an extreme sentiment score from
a low-confidence read never fires an alert, regardless of magnitude.
Alerts are idempotent per `(portfolio_id, news_event_id)` — re-running
`generate_and_persist` never duplicates an alert already raised for the
same event. Each persisted `PortfolioNewsAlert` also creates a
`Notification(type=PORTFOLIO_ALERT)` row (skipped for an ownerless
portfolio — there's no one to notify), reusing the existing
notification model rather than building new delivery infrastructure
(requirement 10 asks for alert *generation*; actual push/email delivery
of `Notification` rows is out of scope here, matching the
already-established `MarketAlert` "generation only" pattern).

## 6. What was live-verified vs. what was only mock/synthetic-tested

**Live-verified: nothing in this milestone.** This sandbox has no
network access to SAHMK or OpenAI (a standing constraint throughout this
project). Every test runs against synthetic, hand-seeded data in an
in-memory SQLite database and a fake LLM client returning deterministic
JSON — never a real API call. No sentiment score, classification, or
impact estimate produced by any test in this milestone is a claim about
real news content or real market reaction.

**What is real, tested code, regardless of data source:** the collection/
cache-dedup/TTL logic, the `external_key` idempotency mechanism, the
similarity-based deduplication, the weighted sentiment aggregation
formula, the `context_builder` integration point, the per-event signal
explainability path, the alert classification thresholds, the REST
layer, the migration. `NewsAnalyzer`'s parsing/clamping/coercion/failure
handling is real code exercised against both well-formed and
deliberately malformed fake-LLM responses — its correctness does not
depend on whether the underlying model call is real or faked to be
verified.

## 7. REST API

All routes follow `src/api/routes/stocks.py`'s conventions: `APIError`
subclasses → `{"error": {"code", "message"}}` envelope, `Depends(get_db)`.

| Route | Access | Notes |
|---|---|---|
| `GET /api/v1/news/{symbol}` | any authenticated user | All persisted events for a symbol (including unanalyzed ones), newest first. |
| `GET /api/v1/news/market` | any authenticated user | Market-wide and government-policy events (`NewsEntityType.MARKET_WIDE`/`GOVERNMENT`), excludes company-specific events. |
| `GET /api/v1/news/sources` | staff only (`require_staff_role(SUPPORT)`) | Every tracked source's reliability score and article count. |
| `POST /api/v1/news/refresh` | staff only | Runs a real collection + dedup + analysis pass synchronously, bounded by `limit` (1-100, default `NEWS_FETCH_LIMIT`). Returns `RefreshSummary` (collected/already_ingested/duplicates/newly_analyzed/analysis_unavailable/analyzer_available) — honestly reports `analyzer_available: false` rather than a fabricated analysis when no LLM key is configured. |
| `GET /api/v1/portfolio/{id}/news-alerts` | portfolio owner | Already-persisted alerts for this portfolio, newest first. 404 (not 403) for another user's portfolio. |
| `POST /api/v1/portfolio/{id}/news-alerts/refresh` | portfolio owner | Re-evaluates currently-held symbols against already-analyzed news and persists any new alerts — does **not** itself collect new news; pair with `POST /news/refresh` (or a scheduled job calling both) to pick up genuinely new articles first. |

## 8. Known limitations (disclosed)

- **Market-wide/government news is not blended into per-symbol decision-
  engine sentiment** — see §4's disclosed scope boundary.
- **Source reliability scores are seeded at a neutral default and only
  change via manual staff override** — no automated, outcome-driven
  reliability calibration exists yet (§5).
- **`POST /news/refresh` and `POST .../news-alerts/refresh` are
  synchronous**, not background jobs — acceptable at this milestone's
  scale (bounded by `limit`/held-symbol count) but not yet the
  `BackgroundTask`/job-runner pattern `backtests.py` and
  `market_intelligence`'s scan already use for larger workloads.
- **No scheduled/recurring refresh job exists yet** — `POST
  /news/refresh` must be explicitly triggered (by staff or an external
  scheduler); this milestone does not add a new `IngestionScheduler`-
  style recurring job, though the existing one's pattern would extend
  cleanly to one.
- **`Notification` rows are generated, not delivered** — no
  push/email/SMS delivery mechanism exists in this codebase for any
  notification type, news alerts included (matching the pre-existing
  `MarketAlert` posture).
- **One LLM call per canonical article, no batching** — acceptable at
  this milestone's scale; a high-volume real deployment would likely
  want batched analysis calls to control LLM cost/latency, not built
  here.
- **The entity/classification/sentiment/impact model itself is only as
  good as the underlying LLM's read of a single headline** — no
  full-article-body ingestion exists (the provider interface returns a
  headline-level payload); this is a data-availability constraint of
  `IMarketDataProvider.get_market_news()`, not something this milestone
  can fix without a richer upstream feed.

## 9. Suggested next milestone

- Wire an existing or new recurring job (reusing the
  `IngestionScheduler` pattern) to call `POST /news/refresh` and
  `POST .../news-alerts/refresh` automatically, rather than requiring
  an explicit staff/external trigger.
- Blend market-wide/government-policy sentiment into per-symbol decision
  scoring (§4's disclosed boundary) — e.g. a sector-level or
  market-wide sentiment adjustment alongside the existing per-company
  one.
- Automated, outcome-driven source reliability calibration, following
  the same significance-tested pattern
  `docs/BACKTESTING_AND_CALIBRATION.md` §5b already built for
  contributor weights.
- Real push/email delivery for `Notification` rows (all types, not just
  news alerts) — a platform-wide gap, not specific to this milestone.
- Batched LLM analysis calls if/when article volume grows enough that
  per-article calls become a cost or latency concern.

This document is superseded by whatever the next milestone's own status
document says, once that work is code-verified.
