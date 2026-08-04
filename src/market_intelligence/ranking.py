"""RankingEngine: turns one scan's `SymbolScanOutcome`s (plus, for six
categories, the prior scan's `ChangeDetectionResult`) into the
seventeen requested ranking lists.

Declarative, not seventeen hand-written methods: eleven categories are
pure filter+sort rules over `outcomes` (`_FILTER_SORT_RULES`, applied
by one shared `_build_from_rule` helper); the remaining six read from
`ChangeDetectionResult` instead (a structurally different data source
-- a symbol's *delta* against the previous scan, not a property of the
current scan alone), handled by one shared `_build_from_changes`
helper parameterized the same way. No ranking category has its own
copy of the filter/sort/entry-building logic.

Rankings are computed on read, not persisted (see
domain/models/symbol_intelligence_record.py's docstring for why) --
`rank()` is a pure function of already-stored `SymbolScanOutcome`/
`ChangeDetectionResult` data, never a database write.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional

from src.analysis.recommendation.types import Recommendation
from src.market_intelligence.config import get_ranking_top_n
from src.market_intelligence.ordinals import RISK_RANK, recommendation_rank_of_value
from src.market_intelligence.publication_gate import is_publishable
from src.market_intelligence.types import (
    ChangeDetectionResult,
    ChangeType,
    RankingCategory,
    RankingEntry,
    RankingList,
    SymbolScanOutcome,
)

_BUY_LIKE = {Recommendation.BUY, Recommendation.STRONG_BUY}
_SELL_LIKE = {Recommendation.SELL, Recommendation.STRONG_SELL}


def _to_entry(outcome: SymbolScanOutcome, rank_value: Optional[float]) -> RankingEntry:
    return RankingEntry(
        symbol=outcome.symbol,
        sector=outcome.sector,
        recommendation=outcome.recommendation.value if outcome.recommendation else None,
        confidence=outcome.confidence,
        final_score=outcome.final_score,
        target_price=outcome.target_price,
        expected_return_pct=outcome.expected_return_pct,
        risk_level=outcome.risk_level.value if outcome.risk_level else None,
        rank_value=rank_value,
    )


@dataclass(frozen=True)
class _FilterSortRule:
    predicate: Callable[[SymbolScanOutcome], bool]
    key_fn: Callable[[SymbolScanOutcome], float]
    reverse: bool


def _successful(outcome: SymbolScanOutcome) -> bool:
    """A symbol can be `success=True` with only a fundamental leg (no
    technical data) -- see scanner.py's `_scan_one` -- which can leave
    `latest_price` at 0/None. Every ranking category is price- or
    score-derived, so such an outcome must never appear in any of
    them, not just the publication-gated "opportunity" ones (found via
    real full-universe evidence: symbol 2210 with latest_price=0.0 and
    no technical leg reached MOST_BEARISH unfiltered). Same threshold
    `publication_gate._price_validity_gate` already applies."""
    return (
        outcome.success
        and outcome.report is not None
        and outcome.latest_price is not None
        and outcome.latest_price > 0
    )


_FILTER_SORT_RULES: Dict[RankingCategory, _FilterSortRule] = {
    RankingCategory.TOP_BUY: _FilterSortRule(
        lambda o: _successful(o) and o.recommendation in _BUY_LIKE and is_publishable(o),
        lambda o: o.final_score, True,
    ),
    RankingCategory.TOP_STRONG_BUY: _FilterSortRule(
        lambda o: _successful(o) and o.recommendation is Recommendation.STRONG_BUY and is_publishable(o),
        lambda o: o.confidence, True,
    ),
    RankingCategory.TOP_LONG_TERM_INVESTMENT: _FilterSortRule(
        lambda o: (
            _successful(o) and o.recommendation in _BUY_LIKE
            and o.time_horizon is not None and o.time_horizon.value == "LONG_TERM"
            and is_publishable(o)
        ),
        lambda o: o.confidence, True,
    ),
    RankingCategory.TOP_SWING_TRADE: _FilterSortRule(
        lambda o: (
            _successful(o) and o.recommendation in _BUY_LIKE
            and o.time_horizon is not None and o.time_horizon.value == "SHORT_TERM"
            and o.expected_return_pct is not None
            and is_publishable(o)
        ),
        lambda o: o.expected_return_pct, True,
    ),
    RankingCategory.TOP_DIVIDEND_STOCKS: _FilterSortRule(
        lambda o: _successful(o) and o.dividend_yield is not None,
        lambda o: o.dividend_yield, True,
    ),
    RankingCategory.HIGHEST_CONFIDENCE: _FilterSortRule(
        _successful, lambda o: o.confidence, True,
    ),
    RankingCategory.HIGHEST_EXPECTED_RETURN: _FilterSortRule(
        lambda o: _successful(o) and o.expected_return_pct is not None,
        lambda o: o.expected_return_pct, True,
    ),
    RankingCategory.LOWEST_RISK: _FilterSortRule(
        lambda o: _successful(o) and o.risk_level is not None,
        lambda o: (RISK_RANK[o.risk_level], -o.confidence), False,
    ),
    RankingCategory.HIGHEST_RISK: _FilterSortRule(
        lambda o: _successful(o) and o.risk_level is not None,
        lambda o: (RISK_RANK[o.risk_level], o.confidence), True,
    ),
    RankingCategory.MOST_BULLISH: _FilterSortRule(
        _successful, lambda o: o.final_score, True,
    ),
    RankingCategory.MOST_BEARISH: _FilterSortRule(
        _successful, lambda o: o.final_score, False,
    ),
}

# category -> (change_type, extra predicate on the event, key_fn over the event's delta, reverse)
_CHANGE_RULES: Dict[RankingCategory, tuple] = {
    RankingCategory.MOST_IMPROVED_TODAY: (ChangeType.SCORE_CHANGE, lambda e: e.delta is not None and e.delta > 0, True),
    RankingCategory.MOST_DETERIORATED_TODAY: (ChangeType.SCORE_CHANGE, lambda e: e.delta is not None and e.delta < 0, False),
    RankingCategory.RECENTLY_UPGRADED: (
        ChangeType.RECOMMENDATION_CHANGE,
        lambda e: recommendation_rank_of_value(e.new_value) > recommendation_rank_of_value(e.previous_value),
        True,
    ),
    RankingCategory.RECENTLY_DOWNGRADED: (
        ChangeType.RECOMMENDATION_CHANGE,
        lambda e: recommendation_rank_of_value(e.new_value) < recommendation_rank_of_value(e.previous_value),
        False,
    ),
}


class RankingEngine:
    def rank(
        self,
        outcomes: List[SymbolScanOutcome],
        change_result: Optional[ChangeDetectionResult] = None,
    ) -> Dict[RankingCategory, RankingList]:
        generated_at = datetime.now(timezone.utc)
        top_n = get_ranking_top_n()
        by_symbol = {o.symbol: o for o in outcomes}

        rankings: Dict[RankingCategory, RankingList] = {}
        for category, rule in _FILTER_SORT_RULES.items():
            rankings[category] = self._build_from_rule(category, outcomes, rule, top_n, generated_at)

        for category in (
            RankingCategory.MOST_IMPROVED_TODAY,
            RankingCategory.MOST_DETERIORATED_TODAY,
            RankingCategory.RECENTLY_UPGRADED,
            RankingCategory.RECENTLY_DOWNGRADED,
        ):
            rankings[category] = self._build_from_changes(category, change_result, by_symbol, top_n, generated_at)

        rankings[RankingCategory.NEW_OPPORTUNITIES] = self._build_new_opportunities(
            change_result, by_symbol, top_n, generated_at
        )
        rankings[RankingCategory.REMOVED_OPPORTUNITIES] = self._build_removed_opportunities(
            change_result, top_n, generated_at
        )
        return rankings

    @staticmethod
    def _build_from_rule(
        category: RankingCategory,
        outcomes: List[SymbolScanOutcome],
        rule: _FilterSortRule,
        top_n: int,
        generated_at: datetime,
    ) -> RankingList:
        matching = [o for o in outcomes if rule.predicate(o)]
        matching.sort(key=rule.key_fn, reverse=rule.reverse)
        entries = [_to_entry(o, _scalar_rank_value(rule.key_fn(o))) for o in matching[:top_n]]
        return RankingList(category=category, entries=entries, generated_at=generated_at)

    @staticmethod
    def _build_from_changes(
        category: RankingCategory,
        change_result: Optional[ChangeDetectionResult],
        by_symbol: Dict[str, SymbolScanOutcome],
        top_n: int,
        generated_at: datetime,
    ) -> RankingList:
        if change_result is None:
            return RankingList(category=category, entries=[], generated_at=generated_at)

        change_type, event_predicate, reverse = _CHANGE_RULES[category]
        matching_events = [
            e for e in change_result.events
            if e.change_type is change_type and e.symbol in by_symbol and event_predicate(e)
        ]
        matching_events.sort(key=lambda e: e.delta if e.delta is not None else 0.0, reverse=reverse)

        entries = [
            _to_entry(by_symbol[e.symbol], e.delta) for e in matching_events[:top_n]
        ]
        return RankingList(category=category, entries=entries, generated_at=generated_at)

    @staticmethod
    def _build_new_opportunities(
        change_result: Optional[ChangeDetectionResult],
        by_symbol: Dict[str, SymbolScanOutcome],
        top_n: int,
        generated_at: datetime,
    ) -> RankingList:
        """A symbol whose recommendation just became BUY/STRONG_BUY --
        either newly seen this scan and already BUY/STRONG_BUY, or
        upgraded into buy territory from something that wasn't."""
        if change_result is None:
            return RankingList(category=RankingCategory.NEW_OPPORTUNITIES, entries=[], generated_at=generated_at)

        candidates = set()
        for symbol in change_result.new_symbols:
            outcome = by_symbol.get(symbol)
            if outcome is not None and _successful(outcome) and outcome.recommendation in _BUY_LIKE and is_publishable(outcome):
                candidates.add(symbol)
        for event in change_result.events:
            if event.change_type is not ChangeType.RECOMMENDATION_CHANGE:
                continue
            new_is_buy = event.new_value in {r.value for r in _BUY_LIKE}
            previous_was_buy = event.previous_value in {r.value for r in _BUY_LIKE}
            candidate_outcome = by_symbol.get(event.symbol)
            if new_is_buy and not previous_was_buy and candidate_outcome is not None and is_publishable(candidate_outcome):
                candidates.add(event.symbol)

        matching = [by_symbol[s] for s in candidates if s in by_symbol]
        matching.sort(key=lambda o: o.final_score, reverse=True)
        entries = [_to_entry(o, o.final_score) for o in matching[:top_n]]
        return RankingList(category=RankingCategory.NEW_OPPORTUNITIES, entries=entries, generated_at=generated_at)

    @staticmethod
    def _build_removed_opportunities(
        change_result: Optional[ChangeDetectionResult],
        top_n: int,
        generated_at: datetime,
    ) -> RankingList:
        """A symbol that *was* BUY/STRONG_BUY as of the previous scan
        and no longer is -- read entirely from the change events (the
        symbol's current outcome, by definition, is no longer a "buy",
        so there is nothing to look up beyond the event itself)."""
        if change_result is None:
            return RankingList(category=RankingCategory.REMOVED_OPPORTUNITIES, entries=[], generated_at=generated_at)

        entries = []
        for event in change_result.events:
            if event.change_type is not ChangeType.RECOMMENDATION_CHANGE:
                continue
            previous_was_buy = event.previous_value in {r.value for r in _BUY_LIKE}
            new_is_buy = event.new_value in {r.value for r in _BUY_LIKE}
            if previous_was_buy and not new_is_buy:
                entries.append(
                    RankingEntry(
                        symbol=event.symbol, sector=None, recommendation=event.new_value,
                        confidence=None, final_score=None, target_price=None,
                        expected_return_pct=None, risk_level=None, rank_value=event.delta,
                    )
                )
        entries = entries[:top_n]
        return RankingList(category=RankingCategory.REMOVED_OPPORTUNITIES, entries=entries, generated_at=generated_at)


def _scalar_rank_value(value) -> Optional[float]:
    """Rule key_fns sometimes sort by a tuple (risk ordinal, tie-break)
    -- RankingEntry.rank_value is documentation, not a sort key, so it
    always reports the single most meaningful number (the first
    element of a tuple key)."""
    if isinstance(value, tuple):
        return float(value[0])
    return float(value) if value is not None else None
