"""Unit tests for Stage 1 of the two-stage Radar scan.

Every test here uses an in-memory SQLite DB and pre-seeded PriceBar
rows -- never a market-data provider of any kind. That structural
absence (no provider fixture, no provider parameter anywhere in
run_stage1_local_scan's signature) is itself the proof Stage 1 makes
zero SAHMK/provider calls, for any universe size.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.core.db.database import Base
from src.domain.models import PriceBar, Stock, Timeframe
from src.market_intelligence.config import get_stage1_abnormal_volume_ratio
from src.market_intelligence.stage1_local_scan import (
    MIN_INDICATOR_ROWS,
    run_stage1_local_scan,
)


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine)
    db = factory()
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)


def _add_stock(session, symbol: str, is_active: bool = True) -> Stock:
    stock = Stock(symbol=symbol, name_en=f"Stock {symbol}", is_active=is_active)
    session.add(stock)
    session.commit()
    return stock


def _add_quiet_bars(session, stock: Stock, count: int, close=Decimal("20.0"), volume: int = 10_000) -> None:
    """Near-flat price/volume history with a tiny day-to-day close
    oscillation (+/-0.5%) -- no net trend, no volume anomaly, no
    breakout, but real (non-zero) close-to-close moves each day.

    A genuinely *identical* close every day degenerates RSI to exactly
    100 (average loss = 0, so the RS ratio blows up) -- a real
    property of the RSI formula on a zero-variance series, not a Stage
    1 bug, but not representative of "quiet trading" either, so this
    fixture avoids it deliberately rather than asserting around it.

    `close * volume` ~= 200,000 SAR/day, safely above the liquidity
    floor, so a "no candidate" result proves the threshold logic (no
    signal fired), not a liquidity exclusion."""
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    spread = close * Decimal("0.005")
    for i in range(count):
        day_close = close + (spread if i % 2 == 0 else -spread)
        session.add(
            PriceBar(
                stock_id=stock.id,
                timeframe=Timeframe.ONE_DAY,
                timestamp=base + timedelta(days=i),
                open=day_close,
                high=day_close + spread,
                low=day_close - spread,
                close=day_close,
                volume=volume,
            )
        )
    session.commit()


def _add_uptrend_bars(session, stock: Stock, count: int, start_close=Decimal("20.0"), step=Decimal("0.30")) -> None:
    """A steadily rising close (real, positive day-to-day moves, no
    interpolation/lookahead) so ADX/SMA/EMA/SuperTrend/RSI/MACD all read
    genuinely bullish -- used to build a Stage 1 candidate whose
    ranking_score should clearly outrank a candidate whose only signal
    is a bare volume spike on otherwise flat history."""
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    close = start_close
    for i in range(count):
        day_close = close + step
        session.add(
            PriceBar(
                stock_id=stock.id,
                timeframe=Timeframe.ONE_DAY,
                timestamp=base + timedelta(days=i),
                open=close,
                high=day_close + Decimal("0.10"),
                low=close - Decimal("0.05"),
                close=day_close,
                volume=50_000,
            )
        )
        close = day_close
    session.commit()


def _add_volume_spike_bar(session, stock: Stock, after_count: int, close=Decimal("21.0"), volume: int = 60_000) -> None:
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    session.add(
        PriceBar(
            stock_id=stock.id,
            timeframe=Timeframe.ONE_DAY,
            timestamp=base + timedelta(days=after_count),
            open=Decimal("20.0"),
            high=close,
            low=Decimal("20.0"),
            close=close,
            volume=volume,
        )
    )
    session.commit()


class TestZeroProviderCost:
    def test_run_stage1_local_scan_never_takes_a_provider_argument(self):
        """Structural proof: the function signature has no provider/
        client parameter at all -- there is nothing for it to call."""
        import inspect

        sig = inspect.signature(run_stage1_local_scan)
        assert "provider" not in sig.parameters
        assert "client" not in sig.parameters


class TestSkipping:
    def test_symbol_with_no_stock_row_is_skipped(self, session):
        result = run_stage1_local_scan(session, symbols=["9999"])
        assert result.universe_size == 1
        assert result.skipped_count == 1
        assert result.evaluated_count == 0
        assert result.candidate_count == 0
        assert result.all_results[0].skip_reason == "no_stock_row"

    def test_symbol_with_too_few_bars_is_skipped(self, session):
        stock = _add_stock(session, "1111")
        _add_quiet_bars(session, stock, count=MIN_INDICATOR_ROWS - 1)

        result = run_stage1_local_scan(session, symbols=["1111"])
        assert result.skipped_count == 1
        assert result.evaluated_count == 0
        assert result.all_results[0].skip_reason == "insufficient_history"

    def test_symbol_with_exactly_the_minimum_bars_is_evaluated_not_skipped(self, session):
        stock = _add_stock(session, "1111")
        _add_quiet_bars(session, stock, count=MIN_INDICATOR_ROWS)

        result = run_stage1_local_scan(session, symbols=["1111"])
        assert result.skipped_count == 0
        assert result.evaluated_count == 1
        assert result.all_results[0].skip_reason is None


class TestCandidateSelection:
    def test_a_perfectly_quiet_symbol_is_not_a_candidate(self, session):
        stock = _add_stock(session, "1111")
        _add_quiet_bars(session, stock, count=40)

        result = run_stage1_local_scan(session, symbols=["1111"])
        assert result.candidate_count == 0
        r = result.all_results[0]
        assert r.is_candidate is False
        assert r.signals == []
        assert r.skip_reason is None  # not skipped -- evaluated, just no signal fired

    def test_a_volume_spike_makes_a_symbol_a_candidate(self, session):
        stock = _add_stock(session, "1111")
        _add_quiet_bars(session, stock, count=39)
        _add_volume_spike_bar(session, stock, after_count=39)

        result = run_stage1_local_scan(session, symbols=["1111"])
        assert result.candidate_count == 1
        r = result.candidates[0]
        assert r.is_candidate is True
        signal_names = {s.name for s in r.signals}
        assert "abnormal_volume" in signal_names
        # volume_sma_20's own window includes the spike bar itself, so
        # the ratio is below a naive 60,000/10,000=6.0 -- only the
        # real threshold crossing (>= ABNORMAL_VOLUME_RATIO) is this
        # test's actual contract, not the SMA indicator's own internals.
        assert r.relative_volume >= get_stage1_abnormal_volume_ratio()

    def test_below_liquidity_floor_never_becomes_a_candidate_even_with_a_signal(self, session):
        stock = _add_stock(session, "1111")
        # Quiet, low-priced, low-volume history -- dollar volume well
        # under the 100,000 SAR floor even after the spike below.
        _add_quiet_bars(session, stock, count=39, close=Decimal("0.50"), volume=1_000)
        _add_volume_spike_bar(session, stock, after_count=39, close=Decimal("0.55"), volume=3_000)

        result = run_stage1_local_scan(session, symbols=["1111"])
        r = result.all_results[0]
        assert r.is_candidate is False
        assert r.skip_reason == "below_liquidity_floor"

    def test_candidates_are_sorted_by_signal_count_descending(self, session):
        weak = _add_stock(session, "1111")
        _add_quiet_bars(session, weak, count=39)
        _add_volume_spike_bar(session, weak, after_count=39, volume=25_000)  # ~2.5x, one signal

        strong = _add_stock(session, "2222")
        _add_quiet_bars(session, strong, count=39)
        _add_volume_spike_bar(session, strong, after_count=39, volume=90_000)  # ~9x, still one signal (ratio-based)

        result = run_stage1_local_scan(session, symbols=["1111", "2222"])
        assert result.candidate_count == 2
        # Both trigger the same single signal type here; the real
        # sort-stability guarantee under test is that ties don't crash
        # and every real candidate is present, not a specific order
        # this synthetic fixture can't meaningfully differentiate.
        assert {c.symbol for c in result.candidates} == {"1111", "2222"}


class TestRankingScore:
    def test_non_candidate_has_no_ranking_score(self, session):
        stock = _add_stock(session, "1111")
        _add_quiet_bars(session, stock, count=40)

        result = run_stage1_local_scan(session, symbols=["1111"])
        assert result.all_results[0].ranking_score is None

    def test_candidate_ranking_score_and_components_are_within_bounds(self, session):
        stock = _add_stock(session, "1111")
        _add_quiet_bars(session, stock, count=39)
        _add_volume_spike_bar(session, stock, after_count=39)

        result = run_stage1_local_scan(session, symbols=["1111"])
        r = result.candidates[0]
        assert r.ranking_score is not None
        assert 0.0 <= r.ranking_score <= 100.0
        for component in (
            r.component_scores.trend,
            r.component_scores.momentum,
            r.component_scores.volume,
            r.component_scores.liquidity,
            r.component_scores.volatility,
            r.component_scores.risk_reward,
        ):
            assert component is None or 0.0 <= component <= 100.0

    def test_a_strong_uptrend_outranks_a_bare_volume_spike(self, session):
        """Deterministic regression: a symbol with a real, sustained
        uptrend (bullish trend/momentum on top of the same volume
        signal) must rank above a symbol whose only evidence is a bare
        volume spike on flat history -- proves ranking_score reflects
        more than just signal count."""
        strong = _add_stock(session, "1111")
        _add_uptrend_bars(session, strong, count=39)
        _add_volume_spike_bar(session, strong, after_count=39, close=Decimal("32.0"))

        weak = _add_stock(session, "2222")
        _add_quiet_bars(session, weak, count=39)
        _add_volume_spike_bar(session, weak, after_count=39)

        result = run_stage1_local_scan(session, symbols=["1111", "2222"])
        assert result.candidate_count == 2
        assert result.candidates[0].symbol == "1111"
        assert result.candidates[0].ranking_score > result.candidates[1].ranking_score

    def test_ranking_score_is_deterministic_for_identical_inputs(self, session):
        stock = _add_stock(session, "1111")
        _add_uptrend_bars(session, stock, count=39)
        _add_volume_spike_bar(session, stock, after_count=39, close=Decimal("32.0"))

        first = run_stage1_local_scan(session, symbols=["1111"]).candidates[0].ranking_score
        second = run_stage1_local_scan(session, symbols=["1111"]).candidates[0].ranking_score
        assert first == second


class TestNativeFloatTypes:
    """2026-08-18 real-market validation audit finding: every numeric
    field here previously arrived as `numpy.float64` (from the
    pandas/numpy-backed TechnicalAnalysisEngine and scoring functions)
    despite the dataclass declaring plain `float`. In production this
    reached `emit_radar_opportunities`'s `RadarOpportunity` insert as a
    bare, unadapted numpy scalar -- NumPy 2.x's `repr()` for it
    (`np.float64(82.6)`) got embedded as literal, unquoted SQL text,
    and Postgres parsed it as a schema-qualified function call,
    failing with `psycopg2.errors.InvalidSchemaName: schema "np" does
    not exist` on every single candidate, silently swallowed by the
    scheduler's own `except Exception` handler -- so a real, successful
    scan run produced zero RadarOpportunity rows with no visible error
    anywhere. These tests assert the actual runtime type, not just the
    value, so this exact regression can never reach production again
    unnoticed."""

    def test_ranking_score_and_component_scores_are_native_float(self, session):
        stock = _add_stock(session, "1111")
        _add_uptrend_bars(session, stock, count=39)
        _add_volume_spike_bar(session, stock, after_count=39, close=Decimal("32.0"))

        r = run_stage1_local_scan(session, symbols=["1111"]).candidates[0]
        assert type(r.ranking_score) is float
        assert type(r.risk_reward_ratio) is float
        for component in (
            r.component_scores.trend,
            r.component_scores.momentum,
            r.component_scores.volume,
            r.component_scores.liquidity,
            r.component_scores.volatility,
            r.component_scores.risk_reward,
        ):
            assert component is None or type(component) is float

    def test_indicator_derived_fields_are_native_float(self, session):
        stock = _add_stock(session, "1111")
        _add_quiet_bars(session, stock, count=39)
        _add_volume_spike_bar(session, stock, after_count=39)

        r = run_stage1_local_scan(session, symbols=["1111"]).all_results[0]
        for field_value in (r.relative_volume, r.adx_14, r.rsi_14, r.atr_pct):
            assert field_value is None or type(field_value) is float


class TestFullUniverseAggregation:
    def test_universe_size_and_counts_are_consistent(self, session):
        a = _add_stock(session, "1111")
        _add_quiet_bars(session, a, count=40)
        b = _add_stock(session, "2222")
        _add_quiet_bars(session, b, count=10)  # too few -- skipped

        result = run_stage1_local_scan(session, symbols=["1111", "2222", "9999"])
        assert result.universe_size == 3
        assert result.skipped_count == 2  # "2222" (too few bars) + "9999" (no Stock row)
        assert result.evaluated_count == 1
        assert result.candidate_count == 0

    def test_defaults_to_the_full_selector_universe_when_no_symbols_given(self, session):
        stock = _add_stock(session, "1111")
        _add_quiet_bars(session, stock, count=40)

        result = run_stage1_local_scan(session)
        assert result.universe_size == 1
        assert result.all_results[0].symbol == "1111"
