"""E6 (part 2 of 2) of the AI Evolution Layer: a daily, non-LLM review
of that day's evaluated recommendations -- plain descriptive
statistics and templated observations, never applied to production
automatically (no code path here modifies a contributor weight, a
calibration, or a recommendation). Functionally independent of the E6
`ReflectionEngine` bug fix in
`src.core.autonomous_intelligence_layer.reflection_engine`, which
reflects on generic agent memory/goals, not specifically on trading
recommendation outcomes -- this module is the purpose-built
recommendation-outcome review the design actually calls for.
"""

from collections import Counter
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from src.domain.models import (
    RecommendationOutcome,
    RecommendationOutcomeStatus,
    RecommendationSnapshot,
    ReflectionReport,
)


def _signal_names(snapshot: RecommendationSnapshot) -> List[str]:
    if not snapshot.signals:
        return []
    return [signal["name"] for signal in snapshot.signals if isinstance(signal, dict) and signal.get("name")]


def _dominant_signal(rows: List[Tuple[RecommendationSnapshot, RecommendationOutcome]]) -> Optional[Tuple[str, int]]:
    counter: Counter = Counter()
    for snapshot, _ in rows:
        counter.update(_signal_names(snapshot))
    if not counter:
        return None
    return counter.most_common(1)[0]


def generate_daily_reflection(session: Session, review_date: Optional[date] = None) -> ReflectionReport:
    """Reviews every `RecommendationOutcome` evaluated on `review_date`
    (default: yesterday, UTC) and writes/updates the corresponding
    `ReflectionReport` row. Idempotent -- re-running for an
    already-reflected-on day updates that row's numbers rather than
    creating a duplicate."""
    review_date = review_date or (datetime.now(timezone.utc).date() - timedelta(days=1))

    rows = (
        session.query(RecommendationSnapshot, RecommendationOutcome)
        .join(RecommendationOutcome, RecommendationOutcome.snapshot_id == RecommendationSnapshot.id)
        .filter(func.date(RecommendationOutcome.evaluated_at) == review_date)
        .all()
    )

    successful_rows = [(s, o) for s, o in rows if o.status is RecommendationOutcomeStatus.SUCCESSFUL]
    failed_rows = [(s, o) for s, o in rows if o.status is RecommendationOutcomeStatus.FAILED]
    partial_count = sum(1 for _, o in rows if o.status is RecommendationOutcomeStatus.PARTIAL)
    expired_count = sum(1 for _, o in rows if o.status is RecommendationOutcomeStatus.EXPIRED)

    successful_count = len(successful_rows)
    failed_count = len(failed_rows)
    decisive_count = successful_count + failed_count
    win_rate = successful_count / decisive_count if decisive_count > 0 else None

    key_findings: List[str] = []
    improvement_suggestions: List[str] = []

    if not rows:
        key_findings.append(f"No recommendations were evaluated on {review_date.isoformat()}.")
    else:
        key_findings.append(
            f"Reviewed {len(rows)} recommendation(s) evaluated on {review_date.isoformat()}: "
            f"{successful_count} successful, {failed_count} failed, {partial_count} partial, {expired_count} expired."
        )

        dominant_failed_signal = _dominant_signal(failed_rows)
        if dominant_failed_signal is not None:
            name, count = dominant_failed_signal
            key_findings.append(f"The signal '{name}' appeared in {count} of {failed_count} failed recommendation(s).")
            if count / failed_count >= 0.5:
                improvement_suggestions.append(
                    f"Signal '{name}' was present in a majority of today's failed recommendations -- "
                    "consider reviewing its historical reliability via src.ai_evolution.pattern_discovery."
                )

        if successful_rows and failed_rows:
            avg_confidence_successful = sum(float(s.confidence_score) for s, _ in successful_rows) / successful_count
            avg_confidence_failed = sum(float(s.confidence_score) for s, _ in failed_rows) / failed_count
            key_findings.append(
                f"Average confidence: {avg_confidence_successful:.1f} on successful calls vs. "
                f"{avg_confidence_failed:.1f} on failed calls."
            )
            if avg_confidence_failed >= avg_confidence_successful - 5.0:
                improvement_suggestions.append(
                    "Confidence did not clearly separate successful from failed recommendations today -- "
                    "consider reviewing confidence calibration (src.ai_evolution.confidence_calibration)."
                )

    report = session.query(ReflectionReport).filter_by(review_date=review_date).one_or_none()
    if report is None:
        report = ReflectionReport(review_date=review_date)
        session.add(report)

    report.recommendations_reviewed = len(rows)
    report.successful_count = successful_count
    report.failed_count = failed_count
    report.partial_count = partial_count
    report.expired_count = expired_count
    report.win_rate = win_rate
    report.key_findings = key_findings
    report.improvement_suggestions = improvement_suggestions

    session.commit()
    return report
