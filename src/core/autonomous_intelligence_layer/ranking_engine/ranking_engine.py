"""
Ranking Engine Module

This module implements the Ranking Engine, which ranks options, candidates, or
solutions based on multiple criteria and scoring mechanisms.
"""

from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import logging


logger = logging.getLogger(__name__)


class RankingMethod(Enum):
    """Enumeration for ranking methods."""
    WEIGHTED_SUM = "weighted_sum"  # Sum of weighted scores
    MULTIPLICATIVE = "multiplicative"  # Product of scores
    LEXICOGRAPHIC = "lexicographic"  # Lexicographic ordering
    BORDA = "borda"  # Borda count method
    TOPSIS = "topsis"  # TOPSIS (Technique for Order Preference by Similarity to Ideal Solution)


@dataclass
class Criterion:
    """Represents a ranking criterion."""
    criterion_id: str
    name: str
    weight: float = 1.0  # Importance weight
    is_maximizing: bool = True  # True if higher is better
    min_value: float = 0.0
    max_value: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RankingItem:
    """Represents an item to be ranked."""
    item_id: str
    name: str
    scores: Dict[str, float]  # criterion_id -> score
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RankingResult:
    """Represents ranking results."""
    ranking_id: str
    items: List[Tuple[str, float]]  # (item_id, final_score) sorted by score
    method: RankingMethod
    criteria: List[Criterion]
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RankingConfig:
    """Configuration for Ranking Engine."""
    default_ranking_method: RankingMethod = RankingMethod.WEIGHTED_SUM
    enable_normalization: bool = True
    enable_tie_breaking: bool = True
    max_rankings: int = 1000


class RankingEngine:
    """
    Ranking Engine for multi-criteria decision making.
    
    The Ranking Engine is responsible for:
    - Ranking items based on multiple criteria
    - Applying various ranking methods
    - Normalizing scores
    - Handling ties
    - Analyzing ranking results
    - Tracking ranking history
    """

    def __init__(self, config: Optional[RankingConfig] = None):
        """
        Initialize the Ranking Engine.
        
        Args:
            config: RankingConfig instance for configuring ranking behavior.
                   If None, uses default config.
        """
        self.config = config or RankingConfig()
        self.rankings: Dict[str, RankingResult] = {}
        self.ranking_history: List[RankingResult] = []

    def rank(
        self,
        ranking_id: str,
        items: List[RankingItem],
        criteria: List[Criterion],
        method: Optional[RankingMethod] = None,
    ) -> Optional[RankingResult]:
        """
        Rank items based on criteria.
        
        Args:
            ranking_id: Unique identifier for the ranking
            items: List of items to rank
            criteria: List of ranking criteria
            method: Optional ranking method (uses default if not provided)
            
        Returns:
            RankingResult if ranking successful, None otherwise
        """
        if not items or not criteria:
            logger.error("Items and criteria are required")
            return None

        method = method or self.config.default_ranking_method

        # Normalize scores if enabled
        if self.config.enable_normalization:
            items = self._normalize_scores(items, criteria)

        # Calculate final scores
        final_scores = self._calculate_final_scores(items, criteria, method)

        # Sort items by score
        sorted_items = sorted(final_scores.items(), key=lambda x: x[1], reverse=True)

        # Handle ties if enabled
        if self.config.enable_tie_breaking:
            sorted_items = self._break_ties(sorted_items, items, criteria)

        # Create ranking result
        result = RankingResult(
            ranking_id=ranking_id,
            items=sorted_items,
            method=method,
            criteria=criteria,
        )

        self.rankings[ranking_id] = result
        self.ranking_history.append(result)

        logger.debug(f"Ranking completed: {ranking_id}")
        return result

    def _normalize_scores(
        self,
        items: List[RankingItem],
        criteria: List[Criterion],
    ) -> List[RankingItem]:
        """
        Normalize scores to 0-1 range.
        
        Args:
            items: List of items with scores
            criteria: List of criteria
            
        Returns:
            List of items with normalized scores
        """
        for criterion in criteria:
            scores = [item.scores.get(criterion.criterion_id, 0) for item in items]
            
            if not scores:
                continue

            min_score = min(scores)
            max_score = max(scores)
            score_range = max_score - min_score

            if score_range == 0:
                # All scores are the same
                for item in items:
                    item.scores[criterion.criterion_id] = 0.5
            else:
                for item in items:
                    original_score = item.scores.get(criterion.criterion_id, 0)
                    normalized = (original_score - min_score) / score_range
                    
                    # Reverse if minimizing
                    if not criterion.is_maximizing:
                        normalized = 1.0 - normalized
                    
                    item.scores[criterion.criterion_id] = normalized

        return items

    def _calculate_final_scores(
        self,
        items: List[RankingItem],
        criteria: List[Criterion],
        method: RankingMethod,
    ) -> Dict[str, float]:
        """
        Calculate final scores for items.
        
        Args:
            items: List of items
            criteria: List of criteria
            method: Ranking method to use
            
        Returns:
            Dictionary of item_id -> final_score
        """
        final_scores = {}

        if method == RankingMethod.WEIGHTED_SUM:
            final_scores = self._weighted_sum(items, criteria)
        elif method == RankingMethod.MULTIPLICATIVE:
            final_scores = self._multiplicative(items, criteria)
        elif method == RankingMethod.LEXICOGRAPHIC:
            final_scores = self._lexicographic(items, criteria)
        elif method == RankingMethod.BORDA:
            final_scores = self._borda(items, criteria)
        elif method == RankingMethod.TOPSIS:
            final_scores = self._topsis(items, criteria)

        return final_scores

    def _weighted_sum(
        self,
        items: List[RankingItem],
        criteria: List[Criterion],
    ) -> Dict[str, float]:
        """Calculate weighted sum scores."""
        scores = {}
        total_weight = sum(c.weight for c in criteria)

        for item in items:
            weighted_score = 0.0
            for criterion in criteria:
                score = item.scores.get(criterion.criterion_id, 0)
                weighted_score += score * (criterion.weight / total_weight)
            scores[item.item_id] = weighted_score

        return scores

    def _multiplicative(
        self,
        items: List[RankingItem],
        criteria: List[Criterion],
    ) -> Dict[str, float]:
        """Calculate multiplicative scores."""
        scores = {}

        for item in items:
            product_score = 1.0
            for criterion in criteria:
                score = item.scores.get(criterion.criterion_id, 0)
                # Avoid zero scores
                score = max(0.01, score)
                product_score *= (score ** (criterion.weight / 10.0))
            scores[item.item_id] = product_score

        return scores

    def _lexicographic(
        self,
        items: List[RankingItem],
        criteria: List[Criterion],
    ) -> Dict[str, float]:
        """Calculate lexicographic scores."""
        scores = {}
        sorted_criteria = sorted(criteria, key=lambda c: c.weight, reverse=True)

        for i, item in enumerate(items):
            lex_score = 0.0
            for j, criterion in enumerate(sorted_criteria):
                score = item.scores.get(criterion.criterion_id, 0)
                lex_score += score * (1.0 / (10 ** j))
            scores[item.item_id] = lex_score

        return scores

    def _borda(
        self,
        items: List[RankingItem],
        criteria: List[Criterion],
    ) -> Dict[str, float]:
        """Calculate Borda count scores."""
        scores = {item.item_id: 0.0 for item in items}

        for criterion in criteria:
            # Rank items by this criterion
            ranked = sorted(
                items,
                key=lambda i: i.scores.get(criterion.criterion_id, 0),
                reverse=True,
            )
            
            # Assign Borda points
            for rank, item in enumerate(ranked):
                points = (len(items) - rank) * criterion.weight
                scores[item.item_id] += points

        return scores

    def _topsis(
        self,
        items: List[RankingItem],
        criteria: List[Criterion],
    ) -> Dict[str, float]:
        """Calculate TOPSIS scores."""
        scores = {}

        # Calculate ideal and anti-ideal solutions
        ideal = {}
        anti_ideal = {}

        for criterion in criteria:
            values = [item.scores.get(criterion.criterion_id, 0) for item in items]
            if criterion.is_maximizing:
                ideal[criterion.criterion_id] = max(values)
                anti_ideal[criterion.criterion_id] = min(values)
            else:
                ideal[criterion.criterion_id] = min(values)
                anti_ideal[criterion.criterion_id] = max(values)

        # Calculate distances
        for item in items:
            distance_to_ideal = 0.0
            distance_to_anti_ideal = 0.0

            for criterion in criteria:
                score = item.scores.get(criterion.criterion_id, 0)
                diff_ideal = (score - ideal[criterion.criterion_id]) ** 2
                diff_anti_ideal = (score - anti_ideal[criterion.criterion_id]) ** 2
                
                distance_to_ideal += diff_ideal * (criterion.weight ** 2)
                distance_to_anti_ideal += diff_anti_ideal * (criterion.weight ** 2)

            distance_to_ideal = distance_to_ideal ** 0.5
            distance_to_anti_ideal = distance_to_anti_ideal ** 0.5

            # Calculate TOPSIS score
            if distance_to_ideal + distance_to_anti_ideal == 0:
                topsis_score = 0.5
            else:
                topsis_score = distance_to_anti_ideal / (distance_to_ideal + distance_to_anti_ideal)

            scores[item.item_id] = topsis_score

        return scores

    def _break_ties(
        self,
        sorted_items: List[Tuple[str, float]],
        items: List[RankingItem],
        criteria: List[Criterion],
    ) -> List[Tuple[str, float]]:
        """Break ties using secondary criteria."""
        # Simple tie-breaking: use first criterion as secondary
        if not criteria:
            return sorted_items

        # Group by score
        score_groups = {}
        for item_id, score in sorted_items:
            if score not in score_groups:
                score_groups[score] = []
            score_groups[score].append(item_id)

        # Break ties within each group
        result = []
        for score in sorted(score_groups.keys(), reverse=True):
            group = score_groups[score]
            if len(group) > 1:
                # Sort by first criterion
                first_criterion = criteria[0]
                sorted_group = sorted(
                    group,
                    key=lambda iid: next(
                        (item.scores.get(first_criterion.criterion_id, 0) for item in items if item.item_id == iid),
                        0
                    ),
                    reverse=True,
                )
                result.extend([(iid, score) for iid in sorted_group])
            else:
                result.extend([(iid, score) for iid in group])

        return result

    def analyze_ranking(self, ranking_id: str) -> Dict[str, Any]:
        """
        Analyze ranking results.
        
        Args:
            ranking_id: The ranking ID
            
        Returns:
            Dictionary containing analysis results
        """
        if ranking_id not in self.rankings:
            logger.error(f"Ranking {ranking_id} not found")
            return {}

        result = self.rankings[ranking_id]
        analysis = {
            "ranking_id": ranking_id,
            "method": result.method.value,
            "total_items": len(result.items),
            "top_item": result.items[0] if result.items else None,
            "bottom_item": result.items[-1] if result.items else None,
            "score_range": 0.0,
            "average_score": 0.0,
            "criteria_count": len(result.criteria),
        }

        if result.items:
            scores = [score for _, score in result.items]
            analysis["score_range"] = max(scores) - min(scores)
            analysis["average_score"] = sum(scores) / len(scores)

        return analysis

    def get_ranking(self, ranking_id: str) -> Optional[RankingResult]:
        """
        Get a ranking result.
        
        Args:
            ranking_id: The ranking ID
            
        Returns:
            RankingResult if found, None otherwise
        """
        return self.rankings.get(ranking_id)

    def get_ranking_history(self) -> List[RankingResult]:
        """
        Get ranking history.
        
        Returns:
            List of ranking results
        """
        return self.ranking_history
