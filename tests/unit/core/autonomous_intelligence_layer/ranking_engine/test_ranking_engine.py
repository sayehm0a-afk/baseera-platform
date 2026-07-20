import pytest
from datetime import datetime, UTC
from src.core.autonomous_intelligence_layer.ranking_engine.ranking_engine import (
    RankingEngine,
    RankingConfig,
    RankingItem,
    Criterion,
    RankingMethod,
    RankingResult
)

@pytest.fixture
def ranking_engine():
    return RankingEngine()

def test_rank_weighted_sum(ranking_engine):
    items = [
        RankingItem("item1", "Item 1", {"crit1": 0.8, "crit2": 0.9}),
        RankingItem("item2", "Item 2", {"crit1": 0.7, "crit2": 0.95}),
    ]
    criteria = [
        Criterion("crit1", "Criterion 1", weight=0.6, is_maximizing=True),
        Criterion("crit2", "Criterion 2", weight=0.4, is_maximizing=True),
    ]
    
    result = ranking_engine.rank("rank1", items, criteria, RankingMethod.WEIGHTED_SUM)
    assert result is not None
    assert result.ranking_id == "rank1"
    assert len(result.items) == 2
    assert result.items[0][0] == "item1" # (0.8*0.6 + 0.9*0.4) = 0.48 + 0.36 = 0.84
    assert result.items[1][0] == "item2" # (0.7*0.6 + 0.95*0.4) = 0.42 + 0.38 = 0.80

def test_rank_multiplicative(ranking_engine):
    items = [
        RankingItem("item1", "Item 1", {"crit1": 0.8, "crit2": 0.9}),
        RankingItem("item2", "Item 2", {"crit1": 0.7, "crit2": 0.95}),
    ]
    criteria = [
        Criterion("crit1", "Criterion 1", weight=0.6, is_maximizing=True),
        Criterion("crit2", "Criterion 2", weight=0.4, is_maximizing=True),
    ]
    
    result = ranking_engine.rank("rank2", items, criteria, RankingMethod.MULTIPLICATIVE)
    assert result is not None
    assert result.ranking_id == "rank2"
    assert len(result.items) == 2
    # item1: (0.8^0.6) * (0.9^0.4) = 0.869 * 0.958 = 0.832
    # item2: (0.7^0.6) * (0.95^0.4) = 0.806 * 0.979 = 0.790
    assert result.items[0][0] == "item1"

def test_rank_lexicographic(ranking_engine):
    items = [
        RankingItem("item1", "Item 1", {"crit1": 0.8, "crit2": 0.9}),
        RankingItem("item2", "Item 2", {"crit1": 0.7, "crit2": 0.95}),
    ]
    criteria = [
        Criterion("crit1", "Criterion 1", weight=0.6, is_maximizing=True),
        Criterion("crit2", "Criterion 2", weight=0.4, is_maximizing=True),
    ]
    
    result = ranking_engine.rank("rank3", items, criteria, RankingMethod.LEXICOGRAPHIC)
    assert result is not None
    assert result.ranking_id == "rank3"
    assert len(result.items) == 2
    assert result.items[0][0] == "item1"

def test_rank_borda(ranking_engine):
    items = [
        RankingItem("item1", "Item 1", {"crit1": 0.8, "crit2": 0.9}),
        RankingItem("item2", "Item 2", {"crit1": 0.7, "crit2": 0.95}),
    ]
    criteria = [
        Criterion("crit1", "Criterion 1", weight=0.6, is_maximizing=True),
        Criterion("crit2", "Criterion 2", weight=0.4, is_maximizing=True),
    ]
    
    result = ranking_engine.rank("rank4", items, criteria, RankingMethod.BORDA)
    assert result is not None
    assert result.ranking_id == "rank4"
    assert len(result.items) == 2
    assert result.items[0][0] == "item1"

def test_rank_topsis(ranking_engine):
    items = [
        RankingItem("item1", "Item 1", {"crit1": 0.8, "crit2": 0.9}),
        RankingItem("item2", "Item 2", {"crit1": 0.7, "crit2": 0.95}),
    ]
    criteria = [
        Criterion("crit1", "Criterion 1", weight=0.6, is_maximizing=True),
        Criterion("crit2", "Criterion 2", weight=0.4, is_maximizing=True),
    ]
    
    result = ranking_engine.rank("rank5", items, criteria, RankingMethod.TOPSIS)
    assert result is not None
    assert result.ranking_id == "rank5"
    assert len(result.items) == 2
    assert result.items[0][0] == "item1"

def test_rank_no_items_or_criteria(ranking_engine):
    result = ranking_engine.rank("rank_empty", [], [])
    assert result is None

def test_normalize_scores(ranking_engine):
    items = [
        RankingItem("item1", "Item 1", {"crit1": 10, "crit2": 100}),
        RankingItem("item2", "Item 2", {"crit1": 20, "crit2": 50}),
    ]
    criteria = [
        Criterion("crit1", "Criterion 1", is_maximizing=True, min_value=0, max_value=100),
        Criterion("crit2", "Criterion 2", is_maximizing=False, min_value=0, max_value=100),
    ]
    
    normalized_items = ranking_engine._normalize_scores(items, criteria)
    assert normalized_items[0].scores["crit1"] == 0.0
    assert normalized_items[0].scores["crit2"] == 0.0
    assert normalized_items[1].scores["crit1"] == 1.0
    assert normalized_items[1].scores["crit2"] == 1.0

def test_break_ties(ranking_engine):
    sorted_items = [("item1", 0.8), ("item2", 0.8), ("item3", 0.7)]
    items = [
        RankingItem("item1", "Item 1", {"crit1": 0.9, "crit2": 0.8}),
        RankingItem("item2", "Item 2", {"crit1": 0.7, "crit2": 0.8}),
        RankingItem("item3", "Item 3", {"crit1": 0.6, "crit2": 0.7}),
    ]
    criteria = [
        Criterion("crit1", "Criterion 1", weight=0.6, is_maximizing=True),
        Criterion("crit2", "Criterion 2", weight=0.4, is_maximizing=True),
    ]
    
    broken_ties = ranking_engine._break_ties(sorted_items, items, criteria)
    assert broken_ties[0][0] == "item1"
    assert broken_ties[1][0] == "item2"

def test_analyze_ranking(ranking_engine):
    items = [
        RankingItem("item1", "Item 1", {"crit1": 0.8, "crit2": 0.9}),
        RankingItem("item2", "Item 2", {"crit1": 0.7, "crit2": 0.95}),
    ]
    criteria = [
        Criterion("crit1", "Criterion 1", weight=0.6, is_maximizing=True),
        Criterion("crit2", "Criterion 2", weight=0.4, is_maximizing=True),
    ]
    ranking_engine.rank("rank1", items, criteria, RankingMethod.WEIGHTED_SUM)
    
    analysis = ranking_engine.analyze_ranking("rank1")
    assert analysis["ranking_id"] == "rank1"
    assert analysis["total_items"] == 2
    assert analysis["top_item"][0] == "item1"
    assert analysis["bottom_item"][0] == "item2"
    assert analysis["criteria_count"] == 2
    assert analysis["score_range"] == pytest.approx(0.2)
    assert analysis["average_score"] == pytest.approx(0.5)

def test_getters(ranking_engine):
    items = [
        RankingItem("item1", "Item 1", {"crit1": 0.8, "crit2": 0.9}),
    ]
    criteria = [
        Criterion("crit1", "Criterion 1", weight=0.6, is_maximizing=True),
    ]
    ranking_engine.rank("rank1", items, criteria, RankingMethod.WEIGHTED_SUM)
    
    assert ranking_engine.get_ranking("rank1") is not None
    assert ranking_engine.get_ranking("nonexistent") is None
    assert len(ranking_engine.get_ranking_history()) == 1
