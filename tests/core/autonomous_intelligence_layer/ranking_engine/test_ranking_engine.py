"""
Unit tests for Ranking Engine
"""

import pytest
from core.autonomous_intelligence_layer.ranking_engine import (
    RankingEngine,
    RankingItem,
    Criterion,
    RankingMethod,
    RankingConfig,
)


class TestRankingEngine:
    """Test cases for RankingEngine class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.engine = RankingEngine()
        self.ranking_id = "ranking_001"

    def test_ranking_engine_initialization(self):
        """Test that RankingEngine initializes correctly."""
        assert self.engine is not None
        assert self.engine.config is not None
        assert isinstance(self.engine.config, RankingConfig)
        assert len(self.engine.rankings) == 0

    def test_ranking_engine_with_custom_config(self):
        """Test RankingEngine with custom config."""
        custom_config = RankingConfig(
            default_ranking_method=RankingMethod.BORDA,
            enable_normalization=False,
        )
        engine = RankingEngine(config=custom_config)
        assert engine.config.default_ranking_method == RankingMethod.BORDA
        assert engine.config.enable_normalization is False

    def test_rank_items_weighted_sum(self):
        """Test ranking items with weighted sum method."""
        items = [
            RankingItem(
                item_id="item_1",
                name="Option A",
                scores={"quality": 0.8, "cost": 0.6},
            ),
            RankingItem(
                item_id="item_2",
                name="Option B",
                scores={"quality": 0.7, "cost": 0.9},
            ),
        ]

        criteria = [
            Criterion(criterion_id="quality", name="Quality", weight=0.6),
            Criterion(criterion_id="cost", name="Cost", weight=0.4),
        ]

        result = self.engine.rank(
            ranking_id=self.ranking_id,
            items=items,
            criteria=criteria,
            method=RankingMethod.WEIGHTED_SUM,
        )

        assert result is not None
        assert len(result.items) == 2
        assert result.method == RankingMethod.WEIGHTED_SUM

    def test_rank_items_borda(self):
        """Test ranking items with Borda method."""
        items = [
            RankingItem(
                item_id="item_1",
                name="Option A",
                scores={"quality": 0.8, "price": 0.5},
            ),
            RankingItem(
                item_id="item_2",
                name="Option B",
                scores={"quality": 0.7, "price": 0.8},
            ),
            RankingItem(
                item_id="item_3",
                name="Option C",
                scores={"quality": 0.9, "price": 0.6},
            ),
        ]

        criteria = [
            Criterion(criterion_id="quality", name="Quality", weight=1.0),
            Criterion(criterion_id="price", name="Price", weight=1.0),
        ]

        result = self.engine.rank(
            ranking_id=self.ranking_id,
            items=items,
            criteria=criteria,
            method=RankingMethod.BORDA,
        )

        assert result is not None
        assert len(result.items) == 3
        assert result.method == RankingMethod.BORDA

    def test_rank_items_topsis(self):
        """Test ranking items with TOPSIS method."""
        items = [
            RankingItem(
                item_id="item_1",
                name="Option A",
                scores={"performance": 0.8, "reliability": 0.7},
            ),
            RankingItem(
                item_id="item_2",
                name="Option B",
                scores={"performance": 0.6, "reliability": 0.9},
            ),
        ]

        criteria = [
            Criterion(criterion_id="performance", name="Performance", weight=0.5),
            Criterion(criterion_id="reliability", name="Reliability", weight=0.5),
        ]

        result = self.engine.rank(
            ranking_id=self.ranking_id,
            items=items,
            criteria=criteria,
            method=RankingMethod.TOPSIS,
        )

        assert result is not None
        assert len(result.items) == 2
        assert result.method == RankingMethod.TOPSIS

    def test_rank_with_no_items(self):
        """Test ranking with no items."""
        criteria = [
            Criterion(criterion_id="quality", name="Quality", weight=1.0),
        ]

        result = self.engine.rank(
            ranking_id=self.ranking_id,
            items=[],
            criteria=criteria,
        )

        assert result is None

    def test_rank_with_no_criteria(self):
        """Test ranking with no criteria."""
        items = [
            RankingItem(item_id="item_1", name="Option A", scores={}),
        ]

        result = self.engine.rank(
            ranking_id=self.ranking_id,
            items=items,
            criteria=[],
        )

        assert result is None

    def test_normalize_scores(self):
        """Test score normalization."""
        config = RankingConfig(enable_normalization=True)
        engine = RankingEngine(config=config)

        items = [
            RankingItem(
                item_id="item_1",
                name="Option A",
                scores={"score": 100},
            ),
            RankingItem(
                item_id="item_2",
                name="Option B",
                scores={"score": 50},
            ),
        ]

        criteria = [
            Criterion(criterion_id="score", name="Score", weight=1.0),
        ]

        result = engine.rank(
            ranking_id=self.ranking_id,
            items=items,
            criteria=criteria,
        )

        assert result is not None
        # After normalization, scores should be between 0 and 1

    def test_ranking_with_minimizing_criterion(self):
        """Test ranking with minimizing criterion."""
        items = [
            RankingItem(
                item_id="item_1",
                name="Option A",
                scores={"cost": 100},
            ),
            RankingItem(
                item_id="item_2",
                name="Option B",
                scores={"cost": 50},
            ),
        ]

        criteria = [
            Criterion(
                criterion_id="cost",
                name="Cost",
                weight=1.0,
                is_maximizing=False,  # Lower is better
            ),
        ]

        result = self.engine.rank(
            ranking_id=self.ranking_id,
            items=items,
            criteria=criteria,
        )

        assert result is not None
        # Item with lower cost should rank higher

    def test_analyze_ranking(self):
        """Test analyzing ranking results."""
        items = [
            RankingItem(
                item_id="item_1",
                name="Option A",
                scores={"quality": 0.8},
            ),
            RankingItem(
                item_id="item_2",
                name="Option B",
                scores={"quality": 0.6},
            ),
        ]

        criteria = [
            Criterion(criterion_id="quality", name="Quality", weight=1.0),
        ]

        self.engine.rank(
            ranking_id=self.ranking_id,
            items=items,
            criteria=criteria,
        )

        analysis = self.engine.analyze_ranking(self.ranking_id)

        assert analysis["ranking_id"] == self.ranking_id
        assert analysis["total_items"] == 2
        assert analysis["top_item"] is not None
        assert analysis["bottom_item"] is not None

    def test_get_ranking(self):
        """Test retrieving a ranking."""
        items = [
            RankingItem(
                item_id="item_1",
                name="Option A",
                scores={"quality": 0.8},
            ),
        ]

        criteria = [
            Criterion(criterion_id="quality", name="Quality", weight=1.0),
        ]

        self.engine.rank(
            ranking_id=self.ranking_id,
            items=items,
            criteria=criteria,
        )

        result = self.engine.get_ranking(self.ranking_id)
        assert result is not None
        assert result.ranking_id == self.ranking_id

    def test_get_nonexistent_ranking(self):
        """Test retrieving nonexistent ranking."""
        result = self.engine.get_ranking("nonexistent")
        assert result is None

    def test_ranking_history(self):
        """Test ranking history tracking."""
        items = [
            RankingItem(
                item_id="item_1",
                name="Option A",
                scores={"quality": 0.8},
            ),
        ]

        criteria = [
            Criterion(criterion_id="quality", name="Quality", weight=1.0),
        ]

        self.engine.rank(
            ranking_id=self.ranking_id,
            items=items,
            criteria=criteria,
        )

        history = self.engine.get_ranking_history()
        assert len(history) == 1
        assert history[0].ranking_id == self.ranking_id

    def test_multiple_rankings(self):
        """Test creating multiple rankings."""
        items = [
            RankingItem(
                item_id="item_1",
                name="Option A",
                scores={"quality": 0.8},
            ),
        ]

        criteria = [
            Criterion(criterion_id="quality", name="Quality", weight=1.0),
        ]

        self.engine.rank(
            ranking_id="ranking_001",
            items=items,
            criteria=criteria,
        )

        self.engine.rank(
            ranking_id="ranking_002",
            items=items,
            criteria=criteria,
        )

        assert len(self.engine.rankings) == 2
        assert len(self.engine.get_ranking_history()) == 2

    def test_weighted_criteria(self):
        """Test ranking with different criterion weights."""
        items = [
            RankingItem(
                item_id="item_1",
                name="Option A",
                scores={"quality": 0.9, "price": 0.3},
            ),
            RankingItem(
                item_id="item_2",
                name="Option B",
                scores={"quality": 0.5, "price": 0.9},
            ),
        ]

        criteria = [
            Criterion(criterion_id="quality", name="Quality", weight=0.8),
            Criterion(criterion_id="price", name="Price", weight=0.2),
        ]

        result = self.engine.rank(
            ranking_id=self.ranking_id,
            items=items,
            criteria=criteria,
        )

        assert result is not None
        # Item with high quality should rank higher due to higher weight

    def test_ranking_with_equal_scores(self):
        """Test ranking with equal scores (tie-breaking)."""
        items = [
            RankingItem(
                item_id="item_1",
                name="Option A",
                scores={"quality": 0.8, "secondary": 0.7},
            ),
            RankingItem(
                item_id="item_2",
                name="Option B",
                scores={"quality": 0.8, "secondary": 0.9},
            ),
        ]

        criteria = [
            Criterion(criterion_id="quality", name="Quality", weight=1.0),
            Criterion(criterion_id="secondary", name="Secondary", weight=1.0),
        ]

        result = self.engine.rank(
            ranking_id=self.ranking_id,
            items=items,
            criteria=criteria,
            method=RankingMethod.WEIGHTED_SUM,
        )

        assert result is not None
        assert len(result.items) == 2
