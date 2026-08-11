# Decision Architecture Review — Multi-Agent Council Question (CONT Phase 8)

## Question being answered

Does Basirah's decision pipeline need a *new* multi-agent trading council
(separate specialist reasoning modules that debate and vote on each
recommendation)? This document is the evidence-based answer, per the
mandate's own instruction: *"Do NOT introduce complexity merely because
'multi-agent' sounds advanced... if specialist modules already effectively
exist, formalize their interfaces rather than rebuilding them."*

## Verdict

**No new multi-agent infrastructure is needed.** Basirah already has two
independent systems that jointly satisfy every capability the mandate asks
for — a deterministic specialist-module core, and an LLM-based advisory
panel with an explicit final-arbiter mechanism. Building a third system
would add cost, latency, and hallucination surface for capability that
already exists and is already in production.

## Inventory: what already exists

### 1. Decision Engine V2's deterministic specialist modules

`src/analysis/decision_v2/` is not a monolith — it is already split into
independently testable specialist modules, each owning one domain:

| Module | Specialist responsibility |
|---|---|
| `scoring.py` / `structure.py` | Technical analysis (trend, momentum, support/resistance) |
| `fundamental_summary.py` | Fundamental analysis (real financial-statement ratios) |
| `news_impact.py` | News/event intelligence (POSITIVE/NEGATIVE/NEUTRAL classification from real collected news, not invented) |
| `market_risk.py` | Market regime (9-state classifier: STRONG_ENTRY...DEFENSIVE_EXIT) |
| `trade_classification.py` | Entry timing/trade-type classification |
| `gates.py` | Risk management + contradiction detection — the **final arbiter** (see below) |
| `reasoning.py` | Decision fusion into one coherent Arabic explanation |

Every one of these runs in milliseconds, is 100% reproducible given the
same inputs, and is covered by deterministic unit tests. This *is* the
"specialist reasoning modules" architecture the mandate describes — it
already exists, under different naming than "agents."

### 2. The Investment Committee (a real, already-deployed multi-agent panel)

`src/ai_evolution/committee/` (built and deployed in a prior mandate,
commits tracked as tasks #317-332) is a genuine 8-agent panel:
technical, fundamental, risk, liquidity/volume, news, market_sentiment,
portfolio_allocation, macro (`agents.py`), combined by a weighted-vote
`ConsensusEngine` (`consensus.py`) into one `ConsensusResult` — agreement
percentage, disagreement percentage, disagreement score, most-optimistic/
most-conservative agent, and a grounded Arabic explanation.

Per `consensus.py`'s own docstring: *"Every number here is arithmetic over
the real stance/confidence values the eight committee agents already
computed — no LLM call, no fabricated score."* Only where an agent
genuinely needs qualitative judgment (news sentiment) does a real LLM call
happen, using the same numeric-grounding discipline (R3) the rest of the
codebase already established in `openai_llm_adapter.py`.

**Wiring**: `InvestmentCommitteeOrchestrator().run_committee(...)` is
called from `GET /api/v1/stocks/{symbol}/decision-v2`
(`src/api/routes/stocks.py:781`), once per real user page view, and its
`ConsensusResult` is returned as a `committee` field alongside the primary
decision. The frontend `CommitteePanel.tsx` is wired into
`StockDetailClient.tsx` and shown to *every* user (not owner-only) — the
agreement/disagreement percentages are already visibly disclosed today.

### 3. A second, separate multi-agent system (disclosed overlap)

`src/ai_evolution/agents/` (`AgentPanelOrchestrator`, News/Sentiment/
Debate/Judge agents — built in an earlier "AI Evolution Layer" mandate,
tasks #199) is a *different* panel, wired into the live market-scan write
path (`MarketIntelligenceRepository.save_symbol_records`), gated behind
`AGENT_PANEL_ENABLED` (defaults to `false` — confirmed in
`src/ai_evolution/config.py:53`, not enabled in production today). Its
purpose is self-learning/reflection (`agent_debate_summary` persisted for
later pattern discovery), not per-request explainability.

This is a real, disclosed architectural overlap: two independently-built
multi-agent subsystems exist in the codebase for two different purposes.
**No consolidation is recommended here** — merging them would be a
speculative rewrite of two currently-stable, tested subsystems with no
evidence the merge improves decision quality, which the mandate explicitly
warns against ("do not rewrite stable subsystems without evidence"). They
are documented here so a future reviewer does not mistake the overlap for
an oversight, and does not build a *third* system without first checking
these two.

## Does a "final arbiter" already reject bullish signals?

Yes — today, deterministically, without needing the LLM committee to be in
the loop at all. `gates.py`'s `evaluate_decision()` is the actual final
arbiter for what `decision` value a user ever sees, and it already
downgrades or blocks a favorable raw score on real evidence:

- `real_data_source` / `data_availability` / `price_validity` /
  `data_freshness` / `market_status_known` / `quote_timestamp_known` —
  data-integrity gates.
- Phase 2B's contradiction, price-limit-proximity, stale-recommendation,
  duplicate-signal, and risk-warning gates (already built and tested) —
  these can and do reject a `STRONG_BUY_CANDIDATE`-scoring symbol down to
  `WAIT_FOR_ENTRY`/`REJECT` when the evidence conflicts, however bullish
  the raw technical/fundamental score alone would suggest.

This satisfies the mandate's literal requirement ("the final arbiter must
be able to reject even with bullish individual signals") using the
existing deterministic gate framework — no new LLM-arbitration layer is
needed to get this property.

## Why the Committee's consensus is not wired as a gate

The Committee currently runs **after** `DecisionV2Snapshot` is persisted
(it needs the snapshot's own ID to attach its opinions), which is after
`evaluate_decision()` has already run. Making committee disagreement able
to *veto* the primary `decision` would require reordering the pipeline —
running the committee before gates evaluate, or adding a second write —
which is a real structural change to a stable, tested pipeline, for a
benefit that is hard to justify today:

1. Several committee agents (technical/fundamental/risk/liquidity_volume/
   portfolio_allocation — see `committee/agents.py`'s `analyze_technical`/
   `analyze_fundamental`/`analyze_risk`/etc.) derive their verdict directly
   from the same already-computed `InvestmentDecision`/`DecisionResult`
   breakdown the primary gates already consult (reusing
   `agents/wrapper_agents.py`'s category-mapping logic) — so in the common
   case, "committee disagrees with gates" would mean "the wrapper
   disagrees with its own source data," not new information.
2. It would introduce LLM latency/availability risk into the primary
   decision path, which today is 100% deterministic and sub-second.
3. Disagreement is already disclosed to the user today (agreement_pct/
   disagreement_pct/disagreement_score, visible on every stock page) —
   the trust-building goal the mandate cares about is already met without
   the structural risk.

**Conclusion: keep the current two-layer design.** Decision Engine V2 +
gates remain the sole authority for the `decision` value (fast,
deterministic, explainable, already gate-rejects bullish-but-flawed
setups). The Investment Committee remains a secondary, always-visible
"does independent expert opinion agree" transparency layer. This is
preserved, not rebuilt, per the mandate's explicit preference.
