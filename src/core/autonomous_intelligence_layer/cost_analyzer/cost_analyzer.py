"""
Cost Analyzer Module

This module implements Cost Analyzer for analyzing operational costs,
cost trends, and cost optimization recommendations.
"""

from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime, UTC
from basirah.src.core.shared_models.base_transaction import BaseTransaction
from enum import Enum
import logging


logger = logging.getLogger(__name__)


class CostCategory(Enum):
    """Enumeration for cost categories."""
    COMPUTE = "compute"  # CPU, GPU, memory
    STORAGE = "storage"  # Database, file storage
    NETWORK = "network"  # Bandwidth, data transfer
    API_CALLS = "api_calls"  # External API calls
    PERSONNEL = "personnel"  # Human resources
    INFRASTRUCTURE = "infrastructure"  # Server, hosting
    LICENSES = "licenses"  # Software licenses
    OTHER = "other"


@dataclass(kw_only=True)
class CostItem(BaseTransaction):
    """Represents a cost item."""
    cost_id: str
    category: CostCategory


@dataclass
class CostAnalysis:
    """Represents cost analysis results."""
    analysis_id: str
    total_cost: float
    cost_by_category: Dict[CostCategory, float]
    cost_trends: Dict[str, float]
    optimization_opportunities: List[str]
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class CostOptimizerConfig:
    """Configuration for Cost Analyzer."""
    enable_trend_analysis: bool = True
    enable_optimization_suggestions: bool = True
    max_cost_items: int = 50000


class CostAnalyzer:
    """
    Cost Analyzer for operational cost analysis and optimization.

    The Cost Analyzer is responsible for:
    - Recording cost items
    - Analyzing costs by category
    - Identifying cost trends
    - Generating optimization recommendations
    - Tracking cost history
    """

    def __init__(self, config: Optional[CostOptimizerConfig] = None):
        """
        Initialize Cost Analyzer.

        Args:
            config: CostOptimizerConfig instance.
                   If None, uses default config.
        """
        self.config = config or CostOptimizerConfig()
        self.cost_items: Dict[str, CostItem] = {}
        self.analyses: Dict[str, CostAnalysis] = {}

    def record_cost(
        self,
        cost_id: str,
        category: CostCategory,
        amount: float,
        description: str,
    ) -> Optional[CostItem]:
        """
        Record a cost item.

        Args:
            cost_id: Unique identifier for the cost
            category: Cost category
            amount: Cost amount
            description: Cost description

        Returns:
            CostItem if recorded successfully, None otherwise
        """
        if len(self.cost_items) >= self.config.max_cost_items:
            logger.error("Maximum cost items limit reached")
            return None

        cost_item = CostItem(
            cost_id=cost_id,
            category=category,
            amount=amount,
            description=description,
        )

        self.cost_items[cost_id] = cost_item
        logger.debug(f"Cost recorded: {cost_id}")
        return cost_item

    def analyze_costs(self, analysis_id: str) -> CostAnalysis:
        """
        Analyze recorded costs.

        Args:
            analysis_id: Unique identifier for the analysis

        Returns:
            CostAnalysis instance
        """
        # Calculate total cost
        total_cost = sum(item.amount for item in self.cost_items.values())

        # Calculate cost by category
        cost_by_category = {}
        for category in CostCategory:
            category_cost = sum(
                item.amount for item in self.cost_items.values()
                if item.category == category
            )
            if category_cost > 0:
                cost_by_category[category] = category_cost

        # Analyze trends
        cost_trends = self._analyze_trends()

        # Generate optimization opportunities
        optimization_opportunities = self._generate_optimization_suggestions(cost_by_category)

        analysis = CostAnalysis(
            analysis_id=analysis_id,
            total_cost=total_cost,
            cost_by_category=cost_by_category,
            cost_trends=cost_trends,
            optimization_opportunities=optimization_opportunities,
        )

        self.analyses[analysis_id] = analysis
        logger.debug(f"Cost analysis completed: {analysis_id}")
        return analysis

    def _analyze_trends(self) -> Dict[str, float]:
        """
        Analyze cost trends.

        Returns:
            Dictionary of cost trends
        """
        trends = {}

        for category in CostCategory:
            category_items = [
                item for item in self.cost_items.values()
                if item.category == category
            ]

            if len(category_items) < 2:
                continue

            # Simple trend: compare recent vs older costs
            sorted_items = sorted(category_items, key=lambda x: x.timestamp)
            mid_point = len(sorted_items) // 2

            old_avg = sum(item.amount for item in sorted_items[:mid_point]) / max(mid_point, 1)
            new_avg = sum(item.amount for item in sorted_items[mid_point:]) / max(len(sorted_items) - mid_point, 1)

            trend_percentage = ((new_avg - old_avg) / max(old_avg, 0.1)) * 100
            trends[category.value] = trend_percentage

        return trends

    def _generate_optimization_suggestions(
        self,
        cost_by_category: Dict[CostCategory, float],
    ) -> List[str]:
        """
        Generate optimization suggestions.

        Args:
            cost_by_category: Cost breakdown by category

        Returns:
            List of optimization suggestions
        """
        suggestions = []

        if not cost_by_category:
            return suggestions

        total_cost = sum(cost_by_category.values())

        # Find high-cost categories
        for category, cost in cost_by_category.items():
            percentage = (cost / total_cost) * 100

            if category == CostCategory.COMPUTE and percentage > 40:
                suggestions.append("Consider optimizing compute resources or using auto-scaling")

            elif category == CostCategory.STORAGE and percentage > 30:
                suggestions.append("Review storage usage and consider archiving old data")

            elif category == CostCategory.API_CALLS and percentage > 25:
                suggestions.append("Optimize API call patterns or consider caching")

            elif category == CostCategory.NETWORK and percentage > 20:
                suggestions.append("Review data transfer patterns and consider CDN")

        return suggestions

    def get_cost_by_category(self) -> Dict[CostCategory, float]:
        """
        Get cost breakdown by category.

        Returns:
            Dictionary of costs by category
        """
        cost_by_category = {}

        for category in CostCategory:
            category_cost = sum(
                item.amount for item in self.cost_items.values()
                if item.category == category
            )
            if category_cost > 0:
                cost_by_category[category] = category_cost

        return cost_by_category

    def get_total_cost(self) -> float:
        """
        Get total cost.

        Returns:
            Total cost amount
        """
        return sum(item.amount for item in self.cost_items.values())

    def get_cost_item(self, cost_id: str) -> Optional[CostItem]:
        """
        Get a cost item.

        Args:
            cost_id: The cost ID

        Returns:
            CostItem if found, None otherwise
        """
        return self.cost_items.get(cost_id)

    def get_analysis(self, analysis_id: str) -> Optional[CostAnalysis]:
        """
        Get a cost analysis.

        Args:
            analysis_id: The analysis ID

        Returns:
            CostAnalysis if found, None otherwise
        """
        return self.analyses.get(analysis_id)
