"""Unit tests for the Tadawul trading calendar -- pure datetime math,
no I/O. Uses fixed, reviewable calendar dates (2026-07-28 is a
Tuesday) rather than `datetime.now()`, so results never depend on
when the suite runs.
"""

from datetime import datetime, timezone

from src.market_intelligence.trading_calendar import (
    TADAWUL_TIMEZONE,
    is_market_open,
    seconds_until_close,
    seconds_until_next_open,
)


def _tadawul(year, month, day, hour=0, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=TADAWUL_TIMEZONE)


class TestIsMarketOpen:
    def test_open_mid_session_on_a_trading_day(self):
        # 2026-07-28 is a Tuesday -- a Tadawul trading day.
        assert is_market_open(_tadawul(2026, 7, 28, 12, 0)) is True

    def test_open_at_the_exact_opening_moment(self):
        assert is_market_open(_tadawul(2026, 7, 28, 10, 0)) is True

    def test_closed_one_minute_before_open(self):
        assert is_market_open(_tadawul(2026, 7, 28, 9, 59)) is False

    def test_closed_at_the_exact_closing_moment(self):
        assert is_market_open(_tadawul(2026, 7, 28, 15, 0)) is False

    def test_closed_after_hours_on_a_trading_day(self):
        assert is_market_open(_tadawul(2026, 7, 28, 20, 0)) is False

    def test_closed_on_friday(self):
        # 2026-07-31 is a Friday -- Tadawul does not trade.
        assert is_market_open(_tadawul(2026, 7, 31, 12, 0)) is False

    def test_closed_on_saturday(self):
        # 2026-08-01 is a Saturday.
        assert is_market_open(_tadawul(2026, 8, 1, 12, 0)) is False

    def test_open_on_sunday(self):
        # 2026-08-02 is a Sunday -- the first trading day of the Tadawul week.
        assert is_market_open(_tadawul(2026, 8, 2, 11, 0)) is True

    def test_a_naive_datetime_is_treated_as_utc(self):
        # 12:00 UTC == 15:00 AST -- exactly market close, so closed.
        naive = datetime(2026, 7, 28, 12, 0)
        assert is_market_open(naive) is False
        # 08:00 UTC == 11:00 AST -- mid-session.
        assert is_market_open(datetime(2026, 7, 28, 8, 0)) is True

    def test_defaults_to_now_when_omitted(self):
        # Only checking it runs without error and returns a bool --
        # the real clock's actual state isn't asserted here.
        assert isinstance(is_market_open(), bool)


class TestSecondsUntilNextOpen:
    def test_zero_when_already_open(self):
        assert seconds_until_next_open(_tadawul(2026, 7, 28, 12, 0)) == 0.0

    def test_same_day_before_open(self):
        # Tuesday 05:00 -> Tuesday 10:00 == 5 hours.
        assert seconds_until_next_open(_tadawul(2026, 7, 28, 5, 0)) == 5 * 3600

    def test_thursday_evening_skips_the_weekend_to_sunday(self):
        # 2026-07-30 (Thursday) 16:00 -> 2026-08-02 (Sunday) 10:00.
        result = seconds_until_next_open(_tadawul(2026, 7, 30, 16, 0))
        expected_days = 2  # Fri 30->31, Sat, then Sunday
        expected = (18 * 3600) + (expected_days * 86400)  # 16:00->24:00 Thu (8h) + Fri+Sat (2d) + 00:00->10:00 Sun (10h)
        assert result == expected

    def test_friday_lands_on_sunday_open(self):
        result = seconds_until_next_open(_tadawul(2026, 7, 31, 9, 0))
        # Friday 09:00 -> Sunday 10:00 == 1 day (Fri->Sat) + 1 day (Sat->Sun) + 10h, minus the 9h already elapsed Friday.
        expected = 2 * 86400 + 10 * 3600 - 9 * 3600
        assert result == expected

    def test_saturday_lands_on_sunday_open(self):
        result = seconds_until_next_open(_tadawul(2026, 8, 1, 0, 0))
        expected = 86400 + 10 * 3600  # to Sunday 00:00, then to 10:00
        assert result == expected


class TestSecondsUntilClose:
    def test_none_when_market_is_closed(self):
        assert seconds_until_close(_tadawul(2026, 7, 31, 12, 0)) is None

    def test_remaining_seconds_mid_session(self):
        # Tuesday 12:00 -> close at 15:00 == 3 hours.
        assert seconds_until_close(_tadawul(2026, 7, 28, 12, 0)) == 3 * 3600

    def test_zero_at_the_exact_closing_moment(self):
        assert seconds_until_close(_tadawul(2026, 7, 28, 15, 0)) is None  # already closed, not "0 seconds left"


class TestTimezoneConversion:
    def test_utc_input_is_converted_to_tadawul_local_time(self):
        # 07:00 UTC == 10:00 AST -- exactly market open.
        assert is_market_open(datetime(2026, 7, 28, 7, 0, tzinfo=timezone.utc)) is True
