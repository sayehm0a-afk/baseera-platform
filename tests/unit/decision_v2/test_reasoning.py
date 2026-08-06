"""Unit tests for reasoning.py -- the Arabic sentence builders and the
confidence-breakdown alias."""

from src.analysis.decision_v2.reasoning import (
    build_decision_summary,
    build_entry_confirmation_conditions,
    build_watch_next_session,
    build_why_not_buy_reasons,
    build_why_not_stronger,
    build_why_now,
    confidence_breakdown,
)
from src.analysis.decision_v2.types import Decision, EntryStatus, GateOutcome, GateStatus


class TestConfidenceBreakdown:
    def test_aliases_the_five_named_sub_scores_in_order(self):
        sub = {
            "trend_score": 80.0,
            "momentum_score": 70.0,
            "liquidity_score": 60.0,
            "market_context_score": 65.0,
            "data_quality_score": 90.0,
        }
        result = confidence_breakdown(sub)
        assert result == (80.0, 70.0, 60.0, 65.0, 90.0)

    def test_missing_keys_become_none_not_zero(self):
        result = confidence_breakdown({})
        assert result == (None, None, None, None, None)


class TestBuildDecisionSummary:
    def test_includes_label_and_rounded_confidence(self):
        summary = build_decision_summary("شراء", 82.4, "مضاربة أسبوعية")
        assert "شراء" in summary
        assert "82" in summary
        assert "مضاربة أسبوعية" in summary


class TestBuildWhyNow:
    def test_buy_candidate_uses_the_first_positive_reason(self):
        text = build_why_now(Decision.BUY_CANDIDATE, ["اتجاه صاعد قوي"], "مناسب الآن")
        assert "اتجاه صاعد قوي" in text
        assert "مناسب الآن" in text

    def test_buy_candidate_without_reasons_still_produces_text(self):
        text = build_why_now(Decision.BUY_CANDIDATE, [], "مناسب الآن")
        assert text != ""

    def test_reject_has_its_own_sentence(self):
        text = build_why_now(Decision.REJECT, [], "غير مناسب للدخول")
        assert "معايير" in text

    def test_insufficient_data_has_its_own_sentence(self):
        text = build_why_now(Decision.INSUFFICIENT_DATA, [], "غير مناسب للدخول")
        assert "كافية" in text


class TestBuildWhyNotStronger:
    def test_strong_buy_candidate_says_it_met_the_bar(self):
        text = build_why_not_stronger(Decision.STRONG_BUY_CANDIDATE, [], [])
        assert "أعلى مستوى" in text

    def test_failed_blocking_gate_is_named(self):
        gates = [GateOutcome(name="risk_reward_minimum", status=GateStatus.FAIL, detail="نسبة العائد إلى المخاطرة غير كافية", blocking=True)]
        text = build_why_not_stronger(Decision.REJECT, gates, [])
        assert "نسبة العائد إلى المخاطرة غير كافية" in text

    def test_falls_back_to_a_warning_when_no_gate_failed(self):
        text = build_why_not_stronger(Decision.BUY_CANDIDATE, [], ["تحذير تجريبي"])
        assert "تحذير تجريبي" in text

    def test_generic_sentence_when_nothing_failed_or_warned(self):
        text = build_why_not_stronger(Decision.BUY_CANDIDATE, [], [])
        assert text != ""


class TestBuildWhyNotBuyReasons:
    def test_empty_for_buy_side_decisions(self):
        assert build_why_not_buy_reasons(Decision.STRONG_BUY_CANDIDATE, ["سبب"], []) == []
        assert build_why_not_buy_reasons(Decision.BUY_CANDIDATE, ["سبب"], []) == []

    def test_includes_real_failed_blocking_gate_details(self):
        gates = [
            GateOutcome(name="min_liquidity", status=GateStatus.FAIL, detail="سيولة غير كافية", blocking=True),
            GateOutcome(name="real_data_source", status=GateStatus.PASS, detail="ok", blocking=True),
        ]
        reasons = build_why_not_buy_reasons(Decision.REJECT, [], gates)
        assert reasons == ["سيولة غير كافية"]

    def test_never_counts_a_non_blocking_failed_gate(self):
        gates = [GateOutcome(name="news_conflict", status=GateStatus.FAIL, detail="تحذير فقط", blocking=False)]
        reasons = build_why_not_buy_reasons(Decision.WATCH, [], gates)
        assert "تحذير فقط" not in reasons

    def test_includes_negative_reasons_after_gate_failures_deduplicated(self):
        gates = [GateOutcome(name="g", status=GateStatus.FAIL, detail="سبب مشترك", blocking=True)]
        reasons = build_why_not_buy_reasons(Decision.HOLD, ["سبب مشترك", "سبب آخر"], gates)
        assert reasons == ["سبب مشترك", "سبب آخر"]

    def test_falls_back_to_a_generic_sentence_when_nothing_failed(self):
        reasons = build_why_not_buy_reasons(Decision.WATCH, [], [])
        assert len(reasons) == 1 and reasons[0] != ""

    def test_caps_at_four_reasons(self):
        gates = [
            GateOutcome(name=f"g{i}", status=GateStatus.FAIL, detail=f"سبب {i}", blocking=True) for i in range(6)
        ]
        reasons = build_why_not_buy_reasons(Decision.REJECT, [], gates)
        assert len(reasons) == 4


class TestBuildEntryConfirmationConditions:
    def test_empty_for_non_actionable_decisions(self):
        assert build_entry_confirmation_conditions(Decision.HOLD, EntryStatus.NOT_SUITABLE, 105.0, 102.0) == []

    def test_wait_for_pullback_names_the_entry_zone_ceiling(self):
        conditions = build_entry_confirmation_conditions(
            Decision.WAIT_FOR_ENTRY, EntryStatus.WAIT_FOR_PULLBACK, 110.0, 102.0
        )
        assert any("102.00" in c for c in conditions)

    def test_ready_now_mentions_holding_above_the_stop(self):
        conditions = build_entry_confirmation_conditions(
            Decision.BUY_CANDIDATE, EntryStatus.READY_NOW, 110.0, 102.0
        )
        assert any("وقف الخسارة" in c for c in conditions)

    def test_resistance_breakout_condition_included_when_a_level_exists(self):
        conditions = build_entry_confirmation_conditions(
            Decision.BUY_CANDIDATE, EntryStatus.READY_NOW, 110.0, 102.0
        )
        assert any("110.00" in c for c in conditions)


class TestBuildWatchNextSession:
    def test_includes_resistance_and_support_when_available(self):
        items = build_watch_next_session(95.0, 105.0, 1.0, [])
        assert any("105.00" in i for i in items)
        assert any("95.00" in i for i in items)

    def test_weak_relative_volume_flagged(self):
        items = build_watch_next_session(None, None, 0.3, [])
        assert any("حجم" in i for i in items)

    def test_never_exceeds_four_items(self):
        items = build_watch_next_session(95.0, 105.0, 0.3, ["تحذير1", "تحذير2", "تحذير3"])
        assert len(items) <= 4
