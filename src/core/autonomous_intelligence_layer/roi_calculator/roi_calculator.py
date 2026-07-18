"""
ROI Calculator Module

This module implements ROI Calculator for calculating return on investment,
payback periods, and investment analysis.
"""

from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import logging


logger = logging.getLogger(__name__)


class InvestmentType(Enum):
    """Enumeration for investment types."""
    INFRASTRUCTURE = "infrastructure"
    TRAINING = "training"
    TOOL = "tool"
    OPTIMIZATION = "optimization"
    RESEARCH = "research"


@dataclass
class Investment:
    """Represents an investment."""
    investment_id: str
    investment_type: InvestmentType
    initial_cost: float
    description: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Return:
    """Represents a return on investment."""
    return_id: str
    investment_id: str
    amount: float
    description: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ROIAnalysis:
    """Represents ROI analysis results."""
    analysis_id: str
    investment_id: str
    total_investment: float
    total_return: float
    net_profit: float
    roi_percentage: float
    payback_period_days: Optional[float]
    roi_status: str  # "POSITIVE", "NEGATIVE", "BREAK_EVEN"
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class ROICalculatorConfig:
    """Configuration for ROI Calculator."""
    currency: str = "USD"
    enable_payback_analysis: bool = True
    max_investments: int = 10000


class ROICalculator:
    """
    ROI Calculator for investment analysis.

    The ROI Calculator is responsible for:
    - Recording investments
    - Recording returns on investments
    - Calculating ROI metrics
    - Analyzing payback periods
    - Generating investment recommendations
    """

    def __init__(self, config: Optional[ROICalculatorConfig] = None):
        """
        Initialize ROI Calculator.

        Args:
            config: ROICalculatorConfig instance.
                   If None, uses default config.
        """
        self.config = config or ROICalculatorConfig()
        self.investments: Dict[str, Investment] = {}
        self.returns: Dict[str, Return] = {}
        self.analyses: Dict[str, ROIAnalysis] = {}

    def record_investment(
        self,
        investment_id: str,
        investment_type: InvestmentType,
        initial_cost: float,
        description: str,
    ) -> Optional[Investment]:
        """
        Record an investment.

        Args:
            investment_id: Unique identifier for the investment
            investment_type: Type of investment
            initial_cost: Initial cost of investment
            description: Investment description

        Returns:
            Investment if recorded successfully, None otherwise
        """
        if len(self.investments) >= self.config.max_investments:
            logger.error("Maximum investments limit reached")
            return None

        investment = Investment(
            investment_id=investment_id,
            investment_type=investment_type,
            initial_cost=initial_cost,
            description=description,
        )

        self.investments[investment_id] = investment
        logger.debug(f"Investment recorded: {investment_id}")
        return investment

    def record_return(
        self,
        return_id: str,
        investment_id: str,
        amount: float,
        description: str,
    ) -> Optional[Return]:
        """
        Record a return on investment.

        Args:
            return_id: Unique identifier for the return
            investment_id: ID of the investment
            amount: Return amount
            description: Return description

        Returns:
            Return if recorded successfully, None otherwise
        """
        if investment_id not in self.investments:
            logger.error(f"Investment {investment_id} not found")
            return None

        return_obj = Return(
            return_id=return_id,
            investment_id=investment_id,
            amount=amount,
            description=description,
        )

        self.returns[return_id] = return_obj
        logger.debug(f"Return recorded: {return_id}")
        return return_obj

    def calculate_roi(self, analysis_id: str, investment_id: str) -> Optional[ROIAnalysis]:
        """
        Calculate ROI for an investment.

        Args:
            analysis_id: Unique identifier for the analysis
            investment_id: ID of the investment

        Returns:
            ROIAnalysis if calculation successful, None otherwise
        """
        if investment_id not in self.investments:
            logger.error(f"Investment {investment_id} not found")
            return None

        investment = self.investments[investment_id]

        # Get all returns for this investment
        investment_returns = [
            r for r in self.returns.values()
            if r.investment_id == investment_id
        ]

        total_return = sum(r.amount for r in investment_returns)
        net_profit = total_return - investment.initial_cost
        roi_percentage = (net_profit / investment.initial_cost * 100) if investment.initial_cost > 0 else 0.0

        # Determine ROI status
        if roi_percentage > 0:
            roi_status = "POSITIVE"
        elif roi_percentage < 0:
            roi_status = "NEGATIVE"
        else:
            roi_status = "BREAK_EVEN"

        # Calculate payback period
        payback_period = None
        if self.config.enable_payback_analysis and investment_returns:
            sorted_returns = sorted(investment_returns, key=lambda r: r.timestamp)
            cumulative_return = 0.0
            for return_obj in sorted_returns:
                cumulative_return += return_obj.amount
                if cumulative_return >= investment.initial_cost:
                    days_diff = (return_obj.timestamp - investment.timestamp).days
                    payback_period = days_diff
                    break

        analysis = ROIAnalysis(
            analysis_id=analysis_id,
            investment_id=investment_id,
            total_investment=investment.initial_cost,
            total_return=total_return,
            net_profit=net_profit,
            roi_percentage=roi_percentage,
            payback_period_days=payback_period,
            roi_status=roi_status,
        )

        self.analyses[analysis_id] = analysis
        logger.debug(f"ROI analysis completed: {analysis_id}")
        return analysis

    def get_investment(self, investment_id: str) -> Optional[Investment]:
        """
        Get an investment.

        Args:
            investment_id: The investment ID

        Returns:
            Investment if found, None otherwise
        """
        return self.investments.get(investment_id)

    def get_return(self, return_id: str) -> Optional[Return]:
        """
        Get a return.

        Args:
            return_id: The return ID

        Returns:
            Return if found, None otherwise
        """
        return self.returns.get(return_id)

    def get_analysis(self, analysis_id: str) -> Optional[ROIAnalysis]:
        """
        Get an ROI analysis.

        Args:
            analysis_id: The analysis ID

        Returns:
            ROIAnalysis if found, None otherwise
        """
        return self.analyses.get(analysis_id)

    def get_investment_returns(self, investment_id: str) -> List[Return]:
        """
        Get all returns for an investment.

        Args:
            investment_id: The investment ID

        Returns:
            List of returns for the investment
        """
        return [r for r in self.returns.values() if r.investment_id == investment_id]

    def compare_investments(
        self,
        investment_ids: List[str],
    ) -> Dict[str, Dict[str, Any]]:
        """
        Compare multiple investments.

        Args:
            investment_ids: List of investment IDs to compare

        Returns:
            Dictionary with comparison results
        """
        comparison = {}

        for inv_id in investment_ids:
            if inv_id not in self.investments:
                continue

            investment = self.investments[inv_id]
            investment_returns = self.get_investment_returns(inv_id)
            total_return = sum(r.amount for r in investment_returns)
            roi_percentage = (
                (total_return - investment.initial_cost) / investment.initial_cost * 100
                if investment.initial_cost > 0
                else 0.0
            )

            comparison[inv_id] = {
                "type": investment.investment_type.value,
                "initial_cost": investment.initial_cost,
                "total_return": total_return,
                "roi_percentage": roi_percentage,
                "return_count": len(investment_returns),
            }

        return comparison

    def get_best_roi_investment(self) -> Optional[str]:
        """
        Get the investment with the best ROI.

        Returns:
            Investment ID with best ROI, or None if no investments
        """
        if not self.investments:
            return None

        best_investment_id = None
        best_roi = float("-inf")

        for inv_id, investment in self.investments.items():
            investment_returns = self.get_investment_returns(inv_id)
            total_return = sum(r.amount for r in investment_returns)
            roi_percentage = (
                (total_return - investment.initial_cost) / investment.initial_cost * 100
                if investment.initial_cost > 0
                else 0.0
            )

            if roi_percentage > best_roi:
                best_roi = roi_percentage
                best_investment_id = inv_id

        return best_investment_id
