"""Unit tests for src.backtesting.walk_forward -- pure date arithmetic,
no database. These are the "no leakage between periods" and "final
test period must remain untouched" regression tests for Phase 4."""

from datetime import date, timedelta

import pytest

from src.backtesting.walk_forward import generate_walk_forward_windows


def test_rejects_unknown_mode():
    with pytest.raises(ValueError, match="mode"):
        generate_walk_forward_windows(date(2026, 1, 1), date(2026, 12, 31), 30, 10, 10, mode="sideways")


@pytest.mark.parametrize("train,validation,test", [(0, 10, 10), (30, 0, 10), (30, 10, 0), (-5, 10, 10)])
def test_rejects_nonpositive_window_sizes(train, validation, test):
    with pytest.raises(ValueError):
        generate_walk_forward_windows(date(2026, 1, 1), date(2026, 12, 31), train, validation, test)


def test_rejects_a_range_too_short_for_even_one_window():
    with pytest.raises(ValueError, match="too short"):
        generate_walk_forward_windows(date(2026, 1, 1), date(2026, 1, 20), train_days=30, validation_days=10, test_days=10)


def test_rejects_nonpositive_step_days():
    with pytest.raises(ValueError, match="step_days"):
        generate_walk_forward_windows(
            date(2026, 1, 1), date(2027, 1, 1), train_days=60, validation_days=20, test_days=20, step_days=0
        )


# --- reserved test period -------------------------------------------


def test_test_period_is_the_last_test_days_of_the_range():
    split = generate_walk_forward_windows(
        date(2026, 1, 1), date(2026, 12, 31), train_days=60, validation_days=20, test_days=30, mode="rolling"
    )
    assert split.test_end == date(2026, 12, 31)
    assert split.test_start == date(2026, 12, 31) - timedelta(days=29)


def test_no_window_ever_touches_the_reserved_test_period():
    split = generate_walk_forward_windows(
        date(2026, 1, 1), date(2026, 12, 31), train_days=45, validation_days=15, test_days=30, mode="rolling"
    )
    assert len(split.windows) > 0
    for window in split.windows:
        assert window.validation_end < split.test_start
        assert window.train_end < split.test_start


def test_final_validation_end_is_strictly_before_test_start():
    split = generate_walk_forward_windows(
        date(2026, 1, 1), date(2026, 12, 31), train_days=45, validation_days=15, test_days=30, mode="expanding"
    )
    assert split.final_validation_end < split.test_start


# --- no leakage within/between windows --------------------------------


def test_train_strictly_precedes_validation_in_every_window():
    split = generate_walk_forward_windows(
        date(2026, 1, 1), date(2026, 12, 31), train_days=45, validation_days=15, test_days=30, mode="rolling"
    )
    for window in split.windows:
        assert window.train_start <= window.train_end
        assert window.train_end < window.validation_start
        assert window.validation_start <= window.validation_end


def test_rolling_windows_do_not_overlap_in_validation_periods():
    split = generate_walk_forward_windows(
        date(2026, 1, 1), date(2026, 12, 31), train_days=45, validation_days=15, test_days=30, mode="rolling"
    )
    for a, b in zip(split.windows, split.windows[1:]):
        assert a.validation_end < b.validation_start


# --- rolling vs expanding ------------------------------------------------


def test_rolling_windows_keep_a_fixed_train_size():
    split = generate_walk_forward_windows(
        date(2026, 1, 1), date(2027, 6, 30), train_days=60, validation_days=20, test_days=30, mode="rolling"
    )
    for window in split.windows:
        assert (window.train_end - window.train_start).days + 1 == 60


def test_rolling_train_start_advances_by_step_days():
    split = generate_walk_forward_windows(
        date(2026, 1, 1), date(2027, 6, 30), train_days=60, validation_days=20, test_days=30, mode="rolling", step_days=20
    )
    for a, b in zip(split.windows, split.windows[1:]):
        assert (b.train_start - a.train_start).days == 20


def test_expanding_windows_share_a_fixed_train_start():
    split = generate_walk_forward_windows(
        date(2026, 1, 1), date(2027, 6, 30), train_days=60, validation_days=20, test_days=30, mode="expanding"
    )
    assert all(window.train_start == date(2026, 1, 1) for window in split.windows)


def test_expanding_windows_grow_in_train_length():
    split = generate_walk_forward_windows(
        date(2026, 1, 1), date(2027, 6, 30), train_days=60, validation_days=20, test_days=30, mode="expanding"
    )
    lengths = [(w.train_end - w.train_start).days for w in split.windows]
    assert lengths == sorted(lengths)
    assert lengths[-1] > lengths[0]


def test_default_step_equals_validation_days():
    with_default = generate_walk_forward_windows(
        date(2026, 1, 1), date(2027, 6, 30), train_days=60, validation_days=25, test_days=30, mode="rolling"
    )
    with_explicit = generate_walk_forward_windows(
        date(2026, 1, 1), date(2027, 6, 30), train_days=60, validation_days=25, test_days=30, mode="rolling", step_days=25
    )
    assert with_default.windows == with_explicit.windows


def test_exactly_one_window_fits_a_tightly_sized_range():
    split = generate_walk_forward_windows(
        date(2026, 1, 1), date(2026, 1, 1) + timedelta(days=60 + 20 + 30 - 1), train_days=60, validation_days=20, test_days=30
    )
    assert len(split.windows) == 1
