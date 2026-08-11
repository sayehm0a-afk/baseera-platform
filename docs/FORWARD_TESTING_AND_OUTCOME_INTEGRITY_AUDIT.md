# Forward-Testing & Outcome-Integrity Audit (CONT Phase 10)

## Scope

Audits the recommendation/outcome tracking pipeline
(`RecommendationSnapshot` + `RecommendationOutcome`,
`src/ai_evolution/outcome_evaluation.py`, and the OWNER-only
`src/ai_evolution/personal_performance.py` dashboard that reads them)
against the mandate's integrity checklist: can a historical
recommendation be silently rewritten, is a decision snapshot preserved
verbatim, is look-ahead bias possible, is survivor bias possible, and
are performance stats built only from real, immutable historical rows.

## 1. Historical recommendations cannot be silently rewritten

Verified structurally, not just by convention:

- No route in `src/api/routes/` exposes `PUT`/`PATCH`/`DELETE` against
  either `RecommendationSnapshot` or `RecommendationOutcome` (grepped
  every route module that imports either model -- zero matches).
- `evaluate_due_outcomes()` (`outcome_evaluation.py`) is the *only*
  code path anywhere in `src/` that mutates a `RecommendationOutcome`
  row, and it only ever selects rows via
  `.filter(RecommendationOutcome.status == PENDING)`. Once a row's
  `status` leaves `PENDING` (SUCCESSFUL/FAILED/PARTIAL/EXPIRED/
  CANCELLED), that same query can never select it again -- immutability
  is enforced by the query filter itself, not merely documented.
- New regression test
  `test_a_terminal_outcome_is_never_silently_rewritten_by_a_later_cycle`
  (`tests/unit/ai_evolution/test_outcome_evaluation.py`) proves this
  directly: a terminal SUCCESSFUL row is left byte-for-byte unchanged
  even when a later price bar arrives that would have classified it
  FAILED had it existed at evaluation time.

## 2. The original decision snapshot is preserved verbatim

`RecommendationSnapshot` has no write path other than its initial
insert (`market_intelligence_repository.py`, `backtesting/engine.py`,
`ai_evolution/paper_trading.py` -- all three only ever `session.add()` a
new row, never `session.query(RecommendationSnapshot)...update(...)`).
`outcome_evaluation.py` only *reads* `RecommendationSnapshot` (to know
what target/stop/recommendation to score against) and never assigns to
any of its columns. New regression test
`test_the_original_snapshot_is_never_mutated_by_outcome_evaluation`
re-reads the snapshot after a full evaluation cycle and asserts every
field (`confidence_score`, `total_score`, `target_price`, `stop_loss`,
`market_price_at_evaluation`, `recommendation`) is identical to what was
written at issuance time.

## 3. No look-ahead bias

`load_forward_price_path()` (`src/backtesting/data_access.py`) is the
only function `outcome_evaluation.py` calls for price data, and its own
docstring states the invariant plainly: bars strictly *after*
`from_date`, "deliberately forward-looking, for scoring a decision
already made... never call this to build an AnalysisContext; only
`load_as_of_dataset()` is safe for that." The original decision itself
is built via the separate as-of-safe data-access layer (Part 1/E1 of the
AI Evolution Layer design), so future price data can influence *scoring
an outcome* (which is legitimate and required) but never *making the
original decision* (which would be look-ahead bias). These are two
different functions with two different, correctly-scoped contracts.

## 4. Survivor bias

The theoretical survivor-bias path -- a `Stock` row disappearing so its
outcomes silently vanish from the performance stats -- is guarded
against even though it cannot occur in production today: `Stock` rows
are never deleted anywhere in this codebase (grepped every
`session.delete(...)` call site; the only hard-deletable models are
`User`, `Announcement`, and watchlist items). If a snapshot's `Stock` or
the snapshot itself were ever missing, `evaluate_due_outcomes()` marks
the row `CANCELLED` explicitly (still counted in `status_counts`) rather
than leaving it perpetually `PENDING` or silently dropping it --
disclosed, not hidden, even for a scenario that is currently
unreachable.

## 5. Performance stats are built only from real, immutable rows

`compute_personal_performance_dashboard()`
(`src/ai_evolution/personal_performance.py`) reads exclusively:
1. `DecisionV2Snapshot` (`scan_run_id IS NOT NULL`) for what was shown
   to the user -- the exact table `personal_scan.select_top_opportunities()`
   already reads, so the distributions describe the real product
   surface.
2. `RecommendationOutcome` joined to `RecommendationSnapshot`
   (`source="live_scan"`, `is_paper_trade=False`) for what actually
   happened.

No field is recomputed from current market data -- every number in the
dashboard traces to a stored column on one of these two tables. Failed
recommendations are never filtered out: `status_counts` tallies every
outcome status including FAILED, and no route or dashboard query
excludes FAILED by default (grepped for any status-hiding filter --
none found). Small-sample honesty is real, not cosmetic:
`small_sample_warning` triggers below `_MIN_GROUP_SAMPLE_SIZE` (10) and
`insufficient_data_message_ar` fires when the outcome sample is empty,
both already wired into the frontend (Phase 3).

## Verdict

No historical recommendation can be silently rewritten, no decision
snapshot is ever mutated after issuance, no look-ahead bias exists in
either the decision or the scoring path, survivor bias is structurally
unreachable and defensively handled anyway, and every owner-facing
performance number is built from real, immutable, already-persisted
outcome data with honest small-sample disclosure. No fabricated
evidence exists anywhere in this pipeline. Two new regression tests
were added to lock in the two integrity guarantees that previously had
no direct test coverage (rewrite-proofing and snapshot immutability);
no other code change was evidence-justified by this audit.
