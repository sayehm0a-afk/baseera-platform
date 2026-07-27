# Autonomous AI Analyst Framework

This document describes the Autonomous AI Analyst Framework milestone:
its architecture, the twelve modules it introduces, how it reuses every
existing analysis/decision engine without duplicating any of their
logic, its REST API, its LLM extension point, and — explicitly — what
has and has not been verified.

**This is not an LLM integration.** Nothing in this codebase connects
to OpenAI, the Claude API, Gemini, or any other external AI model. The
framework builds the complete, production-ready architecture an AI
analyst would use to turn structured analysis into human-quality
investment reasoning — today, every word of that reasoning is produced
by a deterministic, template-based pipeline reading real numbers out of
the engines below it. The one designed extension point for a future LLM
(`LLMAdapter`) is an abstract interface only, proven exclusively by a
no-network test double (`NullLLMAdapter`); no concrete adapter that
calls a real provider exists anywhere in this repository.

No claim in this document should be read as "production ready," "fully
complete," or "AI-generated" in the sense of an external model having
produced any of the reasoning text. This document does not use those
phrases as characterizations of the platform.

## 1. Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  REST layer (src/api/routes/stocks.py)                            │
│  GET /{symbol}/analyst-report?format=json|markdown|text           │
│  reuses _build_analysis_context() unchanged (shared with           │
│  /recommendation and /decision)                                    │
└───────────────────────────────┬────────────────────────────────────┘
                                 ▼
┌──────────────────────────────────────────────────────────────────┐
│ src/analysis/analyst/analyst_engine.AnalystEngine.analyze()        │
│   1. AIDecisionEngine.decide(context)  -- called as a black box,   │
│      unmodified, exactly as /decision already does                 │
│   2. ReasoningPipeline.run(context, decision)                      │
│   -> AnalystReport(symbol, decision, explanation, ...)             │
└───────────────────────────────┬────────────────────────────────────┘
                                 ▼
┌──────────────────────────────────────────────────────────────────┐
│ src/analysis/analyst/reasoning_pipeline.ReasoningPipeline.run()    │
│                                                                      │
│  EvidenceCollector.collect(context, decision) -> Evidence           │
│     (pure reorganization, zero recomputation)                       │
│         │                                                            │
│         ▼                                                            │
│  SignalInterpreter.interpret(evidence) -> InterpretedSignals        │
│     (groups Signals into bullish/bearish/neutral factors,           │
│      derives per-category tilts from DecisionFactorBreakdown)       │
│         │                                                            │
│         ▼                                                            │
│  ConflictResolver.resolve(evidence, interpreted) -> ConflictAssessment │
│     (Technical-vs-Fundamental point spread -> tension level;        │
│      opposing category tilts -> conflicting pairs; alternative      │
│      scenarios)                                                      │
│         │                                                            │
│         ▼                                                            │
│  ConfidenceValidator.validate(evidence, conflict) -> ConfidenceAssessment │
│     (bands InvestmentDecision.confidence -- never recomputes it)    │
│         │                                                            │
│         ▼                                                            │
│  NarrativeBuilder.build_*(evidence, interpreted) -> str             │
│     (technical/fundamental/risk reasoning, target price/stop loss/  │
│      time horizon explanations -- every sentence cites a real       │
│      indicator/ratio/decision value, honest "unavailable" fallback  │
│      when the underlying leg is missing)                            │
│         │  (technical/fundamental/risk reasoning only, and only     │
│         │   if an LLMAdapter was injected -- see §5)                │
│         ▼                                                            │
│  RecommendationComposer.compose(...) -> RecommendationRationale      │
│     (investment summary + final rationale; always deterministic)    │
│         │                                                            │
│         ▼                                                            │
│  ExplanationGenerator.generate(...) -> Explanation                   │
│     (pure assembly -- guarantees all 12 sections are populated)     │
└──────────────────────────────────────────────────────────────────┘
                                 │ formatted by (REST layer only)
                                 ▼
┌──────────────────────────────────────────────────────────────────┐
│ src/analysis/analyst/output_formatter.OutputFormatter               │
│   to_dict() / to_markdown() / to_text()                             │
└──────────────────────────────────────────────────────────────────┘
```

`PromptTemplateManager` (`src/analysis/analyst/prompt_templates.py`) is
the single source of narrative wording, used by both `NarrativeBuilder`
and `RecommendationComposer` — every sentence any of these modules
produces comes from a named template filled with real values, never
free text assembled ad hoc.

### What is reused unmodified

`TechnicalAnalysisEngine`, `FundamentalAnalysisEngine`,
`RecommendationEngine`, and `AIDecisionEngine` are called exactly as
`/recommendation` and `/decision` already call them —
`AnalystEngine.analyze()` calls `AIDecisionEngine.decide()` as a black
box and narrates its already-final `InvestmentDecision`; it computes no
score, target price, stop loss, confidence value, or risk level of its
own. One small, additive, precedented rename was made to enable reuse
without duplication: `ai_decision_engine.py`'s module-private
`_CATEGORY_LABELS` dict became the public `CATEGORY_LABELS`, so
`SignalInterpreter` can translate a `Signal.source`/
`DecisionFactorBreakdown.category` key into the same display label
`AIDecisionEngine` already uses, instead of redefining that mapping. No
other change was made to any pre-existing engine, contributor, route,
or schema.

## 2. The twelve modules

| Module | File | Responsibility |
|---|---|---|
| `AnalystEngine` | `analyst_engine.py` | Entry point: calls `AIDecisionEngine.decide()`, then `ReasoningPipeline.run()`, returns `AnalystReport`. |
| `ReasoningPipeline` | `reasoning_pipeline.py` | Orchestrates every stage below into one `Explanation`; the only module that may call an `LLMAdapter`. |
| `EvidenceCollector` | `evidence_collector.py` | Assembles `Evidence` from `AnalysisContext` + `InvestmentDecision`; pure reorganization. |
| `SignalInterpreter` | `signal_interpreter.py` | Groups `Signal`s into bullish/bearish/neutral `InterpretedFactor`s, ranks by impact, derives per-category tilts. |
| `ConflictResolver` | `conflict_resolver.py` | Detects and narrates disagreement between categories (esp. Technical vs. Fundamental); produces alternative scenarios. |
| `ConfidenceValidator` | `confidence_validator.py` | Bands and narrates `InvestmentDecision.confidence`; never recomputes it. |
| `NarrativeBuilder` | `narrative_builder.py` | Produces technical/fundamental/risk reasoning and target price/stop loss/time horizon explanations, citing real cited values. |
| `RecommendationComposer` | `recommendation_composer.py` | Synthesizes everything into the investment summary and final rationale. |
| `ExplanationGenerator` | `explanation_generator.py` | Pure assembly of all twelve `Explanation` fields; guarantees none are ever missing. |
| `PromptTemplateManager` | `prompt_templates.py` | Deterministic template rendering (`render`) plus LLM-prompt construction (`build_prompt`), both from one source of wording. |
| `LLMAdapter` (abstract) | `llm_adapter.py` | The interface a future LLM integration would implement; ships with no concrete network-calling implementation. |
| `OutputFormatter` | `output_formatter.py` | Renders an `AnalystReport` as a dict (JSON), Markdown, or plain text; pure presentation. |

Every dataclass/enum these modules share (`Evidence`, `InterpretedFactor`,
`InterpretedSignals`, `ConflictAssessment`, `ConfidenceAssessment`,
`RecommendationRationale`, `Explanation`, `AnalystReport`,
`FactorStrength`, `ConfidenceBand`, `TensionLevel`) lives in
`src/analysis/analyst/types.py`.

## 3. The twelve-section explanation

Every `AnalystReport.explanation` always contains all twelve fields,
even when the underlying data was unavailable (in which case the text
says so honestly rather than being omitted):

1. `investment_summary`
2. `technical_reasoning`
3. `fundamental_reasoning`
4. `risk_explanation`
5. `bullish_factors` (list)
6. `bearish_factors` (list)
7. `confidence_explanation`
8. `target_price_explanation`
9. `stop_loss_explanation`
10. `time_horizon_explanation`
11. `alternative_scenarios` (list)
12. `final_recommendation_rationale`

## 4. REST API

`GET /api/v1/stocks/{symbol}/analyst-report` — reuses
`_build_analysis_context()` unchanged (the same helper `/recommendation`
and `/decision` already share). Same graceful-degradation and 422 rules
as those two routes: each leg (technical/fundamental/live price)
degrades independently; a 422 `insufficient_data` is only raised when
*both* the technical and fundamental legs are unavailable.

Query parameters:
- `period_type` (`annual` | `quarterly`, default `annual`) — same as
  `/recommendation`/`/decision`.
- `format` (`json` | `markdown` | `text`, default `json`) — `json`
  returns `AnalystReportOut`; `markdown`/`text` return the same report
  rendered by `OutputFormatter.to_markdown()`/`to_text()` as a plain-text
  response (e.g. for a rendered report view, a log, or an email).

## 5. The LLM extension point (not used in production)

`LLMAdapter` (`src/analysis/analyst/llm_adapter.py`) is an abstract base
class only. `ReasoningPipeline` accepts an optional `llm_adapter`
constructor argument; when `None` (the default, and the only
configuration `AnalystEngine()`'s default construction ever uses),
every section is produced entirely by the deterministic pipeline
described in §1 — no network call of any kind occurs.

If an adapter were ever injected, exactly three sections
(`technical_reasoning`, `fundamental_reasoning`, `risk_explanation`)
would be offered to it for rephrasing, always *after* the deterministic
baseline for that section is already computed — the baseline is passed
into `PromptTemplateManager.build_prompt()` as grounding text, and the
adapter's result is used only if non-empty; otherwise the baseline is
kept. All other sections (`investment_summary`, target price/stop
loss/time horizon explanations, `final_recommendation_rationale`) are
always deterministic, never offered to an adapter, since they are
precise numeric syntheses of the whole decision.

The only implementation of `LLMAdapter` in this codebase is
`NullLLMAdapter` — a no-op, test-only double that echoes its prompt back
instead of calling any model. It exists solely so
`tests/unit/analysis/analyst/test_reasoning_pipeline.py` can prove the
extension point is wired correctly (the pipeline detects, calls, and
correctly falls back around an injected adapter) without connecting to
OpenAI, Claude, Gemini, or any other external AI model. Building a real
adapter is explicitly out of scope for this milestone.

## 6. Known limitations (disclosed)

- **No real LLM integration exists or is called** — see §5. Every word
  of every report in production today comes from the deterministic,
  template-based pipeline.
- **Prose quality is template-based, not free-form.** Sentences are
  filled from a fixed set of named templates
  (`PromptTemplateManager._TEMPLATES`); they read as clear, cited
  investment reasoning, but they are not stylistically varied the way
  free-form generation would be.
- **`join_factors()` lowercases only the first character of the joined
  clause**, not each individual factor — a factor beginning with an
  acronym (e.g. "RSI...") can read slightly awkwardly mid-sentence
  ("...supported by rSI(14)..."). Cosmetic only; the underlying claim
  and cited value are always correct.
- **`ConflictResolver`'s `tension_level` is anchored specifically to the
  Technical-vs-Fundamental point spread**, not a general N-way
  disagreement metric, even though `conflicting_categories` does report
  every opposing pair. This mirrors those two categories' outsized,
  independent weight in `AIDecisionEngine.default_contributors()`.
- **The reconstructed "reference price" in target price/stop loss
  explanations** is derived from `target_price`/`expected_return_pct`
  (or, failing that, the technical engine's Bollinger midpoint) since
  `InvestmentDecision` does not itself store the price it was computed
  against — an approximation, not a stored fact.
- **No batch/multi-symbol report endpoint** — one request produces one
  symbol's report, the same granularity `/recommendation` and
  `/decision` already use.

## 7. What was live-verified vs. what was only mock/synthetic-tested

**Live-verified: nothing in this milestone.** As with every prior
milestone, this sandbox has no network access to SAHMK. Every test
(`tests/unit/analysis/analyst/`, `tests/integration/api/
test_analyst_report_route.py`) runs against hand-built fixtures — fake
`Signal`/`DecisionFactorBreakdown`/`InvestmentDecision` objects, tiny
fake `TechnicalAnalysisResult`/`FundamentalAnalysisResult` doubles, and
synthetic, hand-seeded `PriceBar`/`FundamentalSnapshot` rows in an
in-memory SQLite database via the Dev* providers. No text produced by
any test in this milestone is a claim about real market behavior; every
example report is illustrative of the *mechanism* narrating correctly
over invented data.

**What is real, tested code, regardless of data source:** every
orchestration module's logic (grouping/ranking/banding/conflict
detection/prose assembly), the REST route's graceful-degradation and
422 behavior, the three output formats, and the `LLMAdapter` extension
point's wiring (proven via `NullLLMAdapter`, never a real provider).
These are correctness properties of the *code*, verified with
deterministic fixtures.

## 8. Tests

- **78 unit tests** under `tests/unit/analysis/analyst/` — one file per
  module, each testing that module in complete isolation via hand-built
  fixtures (`tests/unit/analysis/analyst/_fixtures.py`), following the
  same "small fake data, not a real engine run" technique
  `test_ai_decision_engine.py` already established. Includes an explicit
  end-to-end proof that `ReasoningPipeline` correctly calls an injected
  `LLMAdapter` (`NullLLMAdapter`) for exactly the three eligible
  sections and falls back to the deterministic baseline when the
  adapter returns an empty result.
- **8 integration tests** under
  `tests/integration/api/test_analyst_report_route.py` — real FastAPI
  routing, real `AnalystEngine`/`AIDecisionEngine`/`RecommendationEngine`/
  `TechnicalAnalysisEngine`/`FundamentalAnalysisEngine` runs, against an
  in-memory SQLite DB and the Dev* providers (see `conftest.py`). Covers
  the happy path (both legs available), 404, 422 (neither leg
  available), graceful degradation (technical-only), all three
  `format` values, an invalid `format` value, and a check that no
  credential ever appears in the response body.
- **1617 tests pass, 12 skipped, repo-wide** (up from 1531 at the end
  of the Backtesting & Calibration Engine milestone). `flake8 src/
  tests/ main.py` is clean at 0 violations.

No claim in this document should be read as "production ready," "fully
complete," or "100% accurate" — none of those are accurate
characterizations, and this document does not use those phrases as
characterizations of the platform.
