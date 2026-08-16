"""Basirah Radar V2 orchestrator (2026-08-16), Phase A + B + C.

Wires Stage 1 (zero-cost local ranking, `stage1_local_scan.py`) to
Stage 2 (bounded live SAHMK validation, the exact same
`_run_one_bounded_background_cycle` helper `POST .../continue-scan-
cycle` and `POST .../stage2-validate-candidates` already use) and
persists one `RadarOpportunity` row per resulting `DecisionV2Snapshot`
-- applying anti-flapping/dedup against each symbol's current live
opportunity along the way.

Deliberately depends on Stage 2 only through an injected async
callable (`run_bounded_stage2_cycle`) matching
`_run_one_bounded_background_cycle`'s own `(session, caller,
resolve_symbols) -> result` shape, rather than importing that function
directly from `src.api.routes.admin.market_intelligence` -- a route
module is the wrong thing for a domain-layer orchestrator to depend on,
and this keeps every function here testable with a plain in-memory
SQLite session and a fake Stage 2 runner, no FastAPI/Redis/SAHMK
involved. The real route wires the real helper in; see
`src.api.routes.admin.market_intelligence`.

Two structural guarantees this module provides, not by re-implementing
safety logic but by composition:

  * "Never live-query the entire universe" -- `select_stage2_candidates`
    truncates Stage 1's ranked candidate list to
    `get_radar_stage2_candidate_cap()` BEFORE Stage 2 is ever invoked,
    so nothing downstream can spend more than that many live-validation
    slots in one Radar V2 pass, regardless of how large Stage 1's own
    `candidate_count` is that day.
  * "Degrade gracefully rather than consume protected quota" -- Stage 2
    here IS `_run_one_bounded_background_cycle`, which already refuses
    to start (at zero SAHMK cost) when upstream is confirmed exhausted
    or remaining background quota is too low. This module adds no
    second, separately-maintained quota check; a `stage2_executed=False`
    result with its real `stop_reason` is surfaced as-is.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, List, Optional

from sqlalchemy.orm import Session

from src.domain.models import DecisionV2Snapshot, RadarOpportunity
from src.market_intelligence.config import (
    get_confidence_change_threshold,
    get_duplicate_suppression_window_hours,
    get_radar_stage2_candidate_cap,
    get_score_change_threshold,
)
from src.market_intelligence.stage1_local_scan import Stage1SymbolResult, run_stage1_local_scan

# Matches _run_one_bounded_background_cycle(session, caller, resolve_symbols)
# -> an object with at least .executed, .stop_reason, .run_id.
StageTwoRunner = Callable[[Session, str, Callable[[], List[str]]], Awaitable[Any]]


def select_stage2_candidates(candidates: List[Stage1SymbolResult]) -> List[Stage1SymbolResult]:
    """Stage 1's own ranking_score ordering is preserved -- this only
    truncates. `candidates` is expected to already be Stage 1's ranked
    `candidates` list (best first); see `Stage1ScanResult.candidates`."""
    cap = get_radar_stage2_candidate_cap()
    return candidates[:cap]


@dataclass(frozen=True)
class RadarV2EmissionResult:
    emitted: List[RadarOpportunity] = field(default_factory=list)
    suppressed_symbols: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class RadarV2RunResult:
    triggered_at: datetime
    stage1_universe_size: int
    stage1_candidate_count: int
    stage2_candidate_cap: int
    stage2_symbols_selected: List[str]
    stage2_executed: bool
    stage2_stop_reason: Optional[str]
    scan_run_id: Optional[int] = None
    opportunities_emitted: List[RadarOpportunity] = field(default_factory=list)
    opportunities_suppressed_as_duplicate: List[str] = field(default_factory=list)


def _as_naive_utc(value: datetime) -> datetime:
    """SQLite (used throughout this project's tests) does not
    round-trip a timezone-aware `DateTime` faithfully -- a value just
    written tz-aware comes back naive on the next query, the same
    pitfall `MarketIntelligenceRepository.mark_running`'s own docstring
    documents. Comparing two datetimes here always goes through this
    normalizer first, rather than risking a raw compare against
    whichever awareness state a given value happens to carry."""
    return value.replace(tzinfo=None) if value.tzinfo is not None else value


def _current_live_opportunity(session: Session, symbol: str) -> Optional[RadarOpportunity]:
    """The opportunity currently shown as "the" radar call for this
    symbol -- superseded_by_id IS NULL. At most one such row should
    ever exist per symbol by construction (every emission either
    creates the first one or supersedes the previous one), but
    `.order_by(...).first()` is used defensively rather than `.one()`."""
    return (
        session.query(RadarOpportunity)
        .filter(RadarOpportunity.symbol == symbol, RadarOpportunity.superseded_by_id.is_(None))
        .order_by(RadarOpportunity.emitted_at.desc())
        .first()
    )


def _is_material_change(
    prior: RadarOpportunity,
    new_classification: str,
    new_confidence: float,
    new_stage1_score: Optional[float],
) -> bool:
    """Mirrors market_intelligence_repository._is_duplicate_recommendation's
    reasoning (same config thresholds, same "direction/decision change
    is always material" rule) adapted to Radar V2's own fields."""
    if prior.classification != new_classification:
        return True
    if abs(new_confidence - float(prior.confidence_score)) >= get_confidence_change_threshold():
        return True
    if new_stage1_score is not None and prior.stage1_ranking_score is not None:
        if abs(new_stage1_score - float(prior.stage1_ranking_score)) >= get_score_change_threshold():
            return True
    return False


def _ranking_reason_ar(rank: int, candidate: Stage1SymbolResult) -> str:
    """The mandate's explicit explainability requirement: "must be able
    to explain WHY this stock ranked above other candidates." Built
    directly from the same signals Stage 1 already computed -- no new
    inference, no LLM call, just formatting real evidence."""
    if candidate.signals:
        signal_text = "، ".join(s.detail_ar for s in candidate.signals)
        return f"جاء هذا السهم في المرتبة {rank} ضمن قائمة مرشحي الرادار بناءً على: {signal_text}."
    return f"جاء هذا السهم في المرتبة {rank} ضمن قائمة مرشحي الرادار."


def emit_radar_opportunities(
    session: Session,
    scan_run_id: int,
    candidates: List[Stage1SymbolResult],
    emitted_at: Optional[datetime] = None,
) -> RadarV2EmissionResult:
    """Reads the real `DecisionV2Snapshot` rows Stage 2 just wrote for
    `scan_run_id`, matches each back to the Stage 1 candidate that
    earned it a live-validation slot, and persists a `RadarOpportunity`
    row -- unless the symbol's current live opportunity, emitted within
    `get_duplicate_suppression_window_hours()`, already says materially
    the same thing (see `_is_material_change`), in which case the
    candidate is skipped and the prior opportunity stays live. A
    material change (or a stale/expired prior) always emits a fresh row
    and points the prior one's `superseded_by_id` at it -- the prior
    row's own evidence is never edited."""
    emitted_at = emitted_at or datetime.now(timezone.utc)
    by_symbol = {c.symbol: c for c in candidates}
    if not by_symbol:
        return RadarV2EmissionResult()

    snapshots = (
        session.query(DecisionV2Snapshot)
        .filter(
            DecisionV2Snapshot.scan_run_id == scan_run_id,
            DecisionV2Snapshot.symbol.in_(by_symbol.keys()),
        )
        .all()
    )
    snapshot_by_symbol = {s.symbol: s for s in snapshots}

    window_cutoff = emitted_at - timedelta(hours=get_duplicate_suppression_window_hours())
    emitted: List[RadarOpportunity] = []
    suppressed: List[str] = []

    for rank, candidate in enumerate(candidates, start=1):
        snapshot = snapshot_by_symbol.get(candidate.symbol)
        if snapshot is None:
            # Stage 2 did not produce a real DecisionV2Snapshot for this
            # symbol this run (e.g. it failed or was skipped) -- there is
            # no "sufficient evidence" to emit an opportunity from.
            continue

        confidence = float(snapshot.confidence_score)
        prior = _current_live_opportunity(session, candidate.symbol)
        if (
            prior is not None
            and _as_naive_utc(prior.emitted_at) >= _as_naive_utc(window_cutoff)
            and not _is_material_change(prior, snapshot.decision, confidence, candidate.ranking_score)
        ):
            suppressed.append(candidate.symbol)
            continue

        opportunity = RadarOpportunity(
            symbol=candidate.symbol,
            stock_id=snapshot.stock_id,
            decision_v2_snapshot_id=snapshot.id,
            scan_run_id=scan_run_id,
            classification=snapshot.decision,
            classification_label_ar=snapshot.decision_label_ar,
            confidence_score=snapshot.confidence_score,
            price_at_signal=snapshot.current_price,
            stage1_rank=rank,
            stage1_ranking_score=candidate.ranking_score,
            stage1_component_scores={
                "trend": candidate.component_scores.trend,
                "momentum": candidate.component_scores.momentum,
                "volume": candidate.component_scores.volume,
                "liquidity": candidate.component_scores.liquidity,
                "volatility": candidate.component_scores.volatility,
                "risk_reward": candidate.component_scores.risk_reward,
            },
            stage1_signals=[{"name": s.name, "detail_ar": s.detail_ar} for s in candidate.signals],
            stage1_risk_reward_ratio=candidate.risk_reward_ratio,
            ranking_reason_ar=_ranking_reason_ar(rank, candidate),
            emitted_at=emitted_at,
        )
        session.add(opportunity)
        session.flush()  # assigns opportunity.id, needed below

        if prior is not None:
            prior.superseded_by_id = opportunity.id

        emitted.append(opportunity)

    session.commit()
    return RadarV2EmissionResult(emitted=emitted, suppressed_symbols=suppressed)


async def run_radar_v2_cycle(
    session: Session,
    run_bounded_stage2_cycle: StageTwoRunner,
    *,
    now: Optional[datetime] = None,
) -> RadarV2RunResult:
    """The full Radar V2 pass: Stage 1 (zero SAHMK cost) -> hard-capped
    candidate selection -> bounded Stage 2 (via the injected runner) ->
    RadarOpportunity emission with dedup. Every early-exit path
    (`no_stage1_candidates`, or whatever real `stop_reason` Stage 2
    itself returns) makes zero SAHMK requests beyond what Stage 2
    itself may have already spent before refusing -- Stage 1 is always
    free, and Stage 2's own pre-flight checks are all zero-cost too."""
    triggered_at = now or datetime.now(timezone.utc)
    cap = get_radar_stage2_candidate_cap()

    stage1_result = run_stage1_local_scan(session)
    selected = select_stage2_candidates(stage1_result.candidates)
    selected_symbols = [c.symbol for c in selected]

    if not selected_symbols:
        return RadarV2RunResult(
            triggered_at=triggered_at,
            stage1_universe_size=stage1_result.universe_size,
            stage1_candidate_count=stage1_result.candidate_count,
            stage2_candidate_cap=cap,
            stage2_symbols_selected=[],
            stage2_executed=False,
            stage2_stop_reason="no_stage1_candidates",
        )

    stage2_result = await run_bounded_stage2_cycle(session, "radar_v2_scan", lambda: selected_symbols)

    if not getattr(stage2_result, "executed", False):
        return RadarV2RunResult(
            triggered_at=triggered_at,
            stage1_universe_size=stage1_result.universe_size,
            stage1_candidate_count=stage1_result.candidate_count,
            stage2_candidate_cap=cap,
            stage2_symbols_selected=selected_symbols,
            stage2_executed=False,
            stage2_stop_reason=getattr(stage2_result, "stop_reason", None),
        )

    scan_run_id = stage2_result.run_id
    emission = emit_radar_opportunities(session, scan_run_id, selected, emitted_at=triggered_at)

    return RadarV2RunResult(
        triggered_at=triggered_at,
        stage1_universe_size=stage1_result.universe_size,
        stage1_candidate_count=stage1_result.candidate_count,
        stage2_candidate_cap=cap,
        stage2_symbols_selected=selected_symbols,
        stage2_executed=True,
        stage2_stop_reason=None,
        scan_run_id=scan_run_id,
        opportunities_emitted=emission.emitted,
        opportunities_suppressed_as_duplicate=emission.suppressed_symbols,
    )
