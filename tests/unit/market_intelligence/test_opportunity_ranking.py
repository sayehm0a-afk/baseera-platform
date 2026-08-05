from datetime import datetime, timezone

from src.market_intelligence.opportunity_ranking import (
    GATE_EXCLUSION_NOTE_AR,
    OPPORTUNITY_CATEGORIES,
    OPPORTUNITY_LABELS_AR,
    OPPORTUNITY_SCORING_FACTOR_AR,
    curate_opportunity_rankings,
)
from src.market_intelligence.ranking import RankingEngine
from src.market_intelligence.types import RankingCategory, RankingList
from tests.unit.market_intelligence._fixtures import make_decision, make_outcome


def test_exactly_eight_categories_are_defined():
    assert len(OPPORTUNITY_CATEGORIES) == 8
    assert len(set(OPPORTUNITY_CATEGORIES)) == 8


def test_every_opportunity_category_has_an_arabic_label_and_scoring_factor():
    for category in OPPORTUNITY_CATEGORIES:
        assert OPPORTUNITY_LABELS_AR[category]
        assert OPPORTUNITY_SCORING_FACTOR_AR[category]


def test_curate_selects_exactly_the_eight_categories_in_order():
    outcomes = [make_outcome(symbol="A", decision=make_decision(symbol="A"))]
    all_rankings = RankingEngine().rank(outcomes)

    curated = curate_opportunity_rankings(all_rankings)

    assert [c.category for c in curated] == OPPORTUNITY_CATEGORIES


def test_curate_attaches_label_scoring_factor_and_gate_note_to_each_entry():
    outcomes = [make_outcome(symbol="A", decision=make_decision(symbol="A"))]
    all_rankings = RankingEngine().rank(outcomes)

    curated = curate_opportunity_rankings(all_rankings)

    for entry in curated:
        assert entry.label_ar == OPPORTUNITY_LABELS_AR[entry.category]
        assert entry.scoring_factor_ar == OPPORTUNITY_SCORING_FACTOR_AR[entry.category]
        assert entry.gate_exclusion_note_ar == GATE_EXCLUSION_NOTE_AR
        assert entry.ranking_list is all_rankings[entry.category]


def test_curate_skips_missing_categories_when_given_a_filtered_dict():
    outcomes = [make_outcome(symbol="A", decision=make_decision(symbol="A"))]
    all_rankings = RankingEngine().rank(outcomes)
    filtered = {RankingCategory.TOP_BUY: all_rankings[RankingCategory.TOP_BUY]}

    curated = curate_opportunity_rankings(filtered)

    assert [c.category for c in curated] == [RankingCategory.TOP_BUY]


def test_curate_keeps_categories_with_zero_publishable_entries():
    """Phase 2I: a scan where every symbol was gate-rejected (or a scan
    with zero symbols) must still produce all 8 categories with an
    empty entries list -- 'no opportunity' is a valid, real result,
    never a reason to drop or error the category."""
    empty_rankings = {
        category: RankingList(category=category, entries=[], generated_at=datetime.now(timezone.utc))
        for category in OPPORTUNITY_CATEGORIES
    }

    curated = curate_opportunity_rankings(empty_rankings)

    assert [c.category for c in curated] == OPPORTUNITY_CATEGORIES
    for entry in curated:
        assert entry.ranking_list.entries == []
        assert entry.gate_exclusion_note_ar == GATE_EXCLUSION_NOTE_AR
        assert entry.label_ar
        assert entry.scoring_factor_ar


def test_diagnostic_only_categories_are_not_among_the_eight():
    diagnostic_only = {
        RankingCategory.HIGHEST_CONFIDENCE,
        RankingCategory.HIGHEST_RISK,
        RankingCategory.MOST_IMPROVED_TODAY,
        RankingCategory.MOST_DETERIORATED_TODAY,
        RankingCategory.RECENTLY_UPGRADED,
        RankingCategory.RECENTLY_DOWNGRADED,
        RankingCategory.REMOVED_OPPORTUNITIES,
        RankingCategory.TOP_LONG_TERM_INVESTMENT,
        RankingCategory.TOP_SWING_TRADE,
    }
    assert diagnostic_only.isdisjoint(set(OPPORTUNITY_CATEGORIES))
