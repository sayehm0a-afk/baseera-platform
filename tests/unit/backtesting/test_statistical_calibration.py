"""Unit tests for src.backtesting.calibration.statistical_calibration.

`significance_test` is tested with hand-built deterministic P&L series
(no database). `propose_statistical_weights` is tested end to end
against an in-memory SQLite DB seeded with real price data, the same
pattern test_engine.py/test_indicator_attribution.py already use.
"""

import math
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.backtesting.calibration.parameters import contributor_class, contributor_names
from src.backtesting.calibration.statistical_calibration import (
    DEFAULT_MIN_SAMPLE_SIZE,
    _propose_weight,
    propose_statistical_weights,
    significance_test,
)
from src.core.db.database import Base
from src.domain.models import DataProvenanceMode, PriceBar, Stock, Timeframe


# --- contributor_names / contributor_class (parameters.py) ----------------


def test_contributor_names_covers_every_known_contributor():
    names = contributor_names()
    assert names == sorted(names)
    assert "technical" in names
    assert "fundamental" in names
    assert len(names) == 11


def test_contributor_class_returns_the_right_class():
    from src.analysis.recommendation.technical_contributor import TechnicalScoreContributor

    assert contributor_class("technical") is TechnicalScoreContributor


def test_contributor_class_rejects_unknown_name():
    with pytest.raises(KeyError):
        contributor_class("not_a_real_contributor")


# --- significance_test ---------------------------------------------------


def test_significance_insufficient_sample_size():
    result = significance_test([1.0])
    assert result.sample_size == 1
    assert result.significant is False
    assert result.p_value is None


def test_significance_zero_variance_is_not_significant():
    result = significance_test([2.0] * 40)
    assert result.mean_edge == pytest.approx(2.0)
    assert result.t_statistic is None
    assert result.significant is False


def test_significance_strong_positive_edge_is_significant():
    values = [5.0 + (i % 3 - 1) * 0.1 for i in range(50)]  # mean ~5.0, tiny variance
    result = significance_test(values)
    assert result.mean_edge == pytest.approx(5.0, abs=0.1)
    assert result.p_value < 0.001
    assert result.significant is True


def test_significance_noisy_zero_mean_is_not_significant():
    values = [1.0, -1.0] * 20  # mean exactly 0
    result = significance_test(values)
    assert result.mean_edge == pytest.approx(0.0)
    assert result.significant is False


def test_significance_below_min_sample_size_is_never_significant_even_with_a_low_p_value():
    values = [5.0 + (i % 3 - 1) * 0.1 for i in range(10)]  # same tight distribution, fewer points
    result = significance_test(values, min_sample_size=30)
    assert result.p_value is not None and result.p_value < 0.05  # arithmetic says significant...
    assert result.significant is False  # ...but sample size floor overrides it


def test_significance_custom_thresholds():
    values = [1.0 + (i % 3 - 1) * 0.05 for i in range(15)]
    lenient = significance_test(values, min_sample_size=10, significance_level=0.10)
    assert lenient.significant is True


# --- _propose_weight -------------------------------------------------------


def test_propose_weight_positive_t_statistic_increases_weight():
    from src.backtesting.calibration.statistical_calibration import SignificanceResult

    sig = SignificanceResult(sample_size=40, mean_edge=1.0, t_statistic=10.0, p_value=0.0001, significant=True)
    new_weight = _propose_weight(0.20, sig)
    assert new_weight > 0.20


def test_propose_weight_negative_t_statistic_decreases_weight():
    from src.backtesting.calibration.statistical_calibration import SignificanceResult

    sig = SignificanceResult(sample_size=40, mean_edge=-1.0, t_statistic=-10.0, p_value=0.0001, significant=True)
    new_weight = _propose_weight(0.20, sig)
    assert new_weight < 0.20


def test_propose_weight_is_bounded_and_floored():
    from src.backtesting.calibration.statistical_calibration import SignificanceResult

    strongly_negative = SignificanceResult(sample_size=40, mean_edge=-5.0, t_statistic=-100.0, p_value=0.0, significant=True)
    new_weight = _propose_weight(0.02, strongly_negative)
    assert new_weight >= 0.01  # floored, never zero or negative


# --- propose_statistical_weights: full DB integration ---------------------


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    db = session_factory()
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)


def _seed_stock_with_oscillating_bars(session, symbol="2222", count=300):
    stock = Stock(symbol=symbol, name_en=f"Stock {symbol}", sector="Energy")
    session.add(stock)
    session.commit()
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i in range(count):
        price = 30.0 + i * 0.05 + math.sin(i / 5.0) * 1.5
        session.add(
            PriceBar(
                stock_id=stock.id, timeframe=Timeframe.ONE_DAY, timestamp=base + timedelta(days=i),
                open=Decimal(str(round(price, 4))), high=Decimal(str(round(price + 0.3, 4))),
                low=Decimal(str(round(price - 0.3, 4))), close=Decimal(str(round(price, 4))),
                volume=1000 + i * 3, source="dev-synthetic", is_synthetic=True,
            )
        )
    session.commit()
    return stock


def test_propose_statistical_weights_covers_every_contributor(session):
    _seed_stock_with_oscillating_bars(session)
    report = propose_statistical_weights(
        session, ["2222"], date(2026, 3, 1), date(2026, 9, 1), DataProvenanceMode.SYNTHETIC,
        evaluation_frequency_days=5, holding_horizon_days=15,
    )
    assert {e.contributor for e in report.entries} == set(contributor_names())
    assert all(e.action in ("reweighted", "unchanged_insufficient_evidence", "unchanged_not_significant") for e in report.entries)


def test_propose_statistical_weights_external_factor_contributors_have_no_backtestable_data(session):
    # news/macro/insider/sector-rotation have no real feed wired into
    # data_access.py's AsOfDataset -- they should honestly report zero
    # sample size, not a fabricated significance result.
    _seed_stock_with_oscillating_bars(session)
    report = propose_statistical_weights(
        session, ["2222"], date(2026, 3, 1), date(2026, 9, 1), DataProvenanceMode.SYNTHETIC,
        evaluation_frequency_days=5, holding_horizon_days=15,
    )
    for name in ("news_sentiment", "macro", "insider_transactions", "sector_rotation"):
        entry = next(e for e in report.entries if e.contributor == name)
        assert entry.sample_size == 0
        assert entry.action == "unchanged_insufficient_evidence"
        assert entry.new_weight == entry.old_weight


def test_contributor_weights_property_only_includes_reweighted_entries(session):
    _seed_stock_with_oscillating_bars(session)
    report = propose_statistical_weights(
        session, ["2222"], date(2026, 3, 1), date(2026, 9, 1), DataProvenanceMode.SYNTHETIC,
        evaluation_frequency_days=5, holding_horizon_days=15,
    )
    weights = report.contributor_weights
    reweighted_names = {e.contributor for e in report.entries if e.action == "reweighted"}
    assert set(weights.keys()) == reweighted_names
    for name, weight in weights.items():
        entry = next(e for e in report.entries if e.contributor == name)
        assert weight == entry.new_weight


def test_propose_statistical_weights_unchanged_entries_keep_exact_old_weight(session):
    _seed_stock_with_oscillating_bars(session)
    report = propose_statistical_weights(
        session, ["2222"], date(2026, 3, 1), date(2026, 9, 1), DataProvenanceMode.SYNTHETIC,
        evaluation_frequency_days=5, holding_horizon_days=15,
    )
    for entry in report.entries:
        if entry.action != "reweighted":
            assert entry.new_weight == entry.old_weight


def test_propose_statistical_weights_respects_min_sample_size_override(session):
    _seed_stock_with_oscillating_bars(session)
    strict_report = propose_statistical_weights(
        session, ["2222"], date(2026, 3, 1), date(2026, 9, 1), DataProvenanceMode.SYNTHETIC,
        evaluation_frequency_days=5, holding_horizon_days=15, min_sample_size=100_000,
    )
    # An impossibly high sample-size floor means nothing can ever qualify.
    assert all(e.action != "reweighted" for e in strict_report.entries)
    assert DEFAULT_MIN_SAMPLE_SIZE < 100_000
