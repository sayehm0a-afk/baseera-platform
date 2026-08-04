"""Unit tests for src.market_intelligence.market_status -- pure
datetime math layered on trading_calendar, no I/O. Uses fixed dates
(2026-07-28 is a Tuesday) rather than datetime.now().
"""

from datetime import datetime

from src.market_intelligence.market_status import MarketSessionStatus, get_market_status
from src.market_intelligence.trading_calendar import TADAWUL_TIMEZONE


def _tadawul(year, month, day, hour=0, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=TADAWUL_TIMEZONE)


class TestGetMarketStatus:
    def test_open_mid_session(self):
        info = get_market_status(_tadawul(2026, 7, 28, 12, 0))
        assert info.status == MarketSessionStatus.OPEN
        assert info.label_ar == "السوق مفتوح"
        assert info.is_trading_day is True
        assert info.seconds_until_close == 3 * 3600

    def test_pre_open_auction(self):
        info = get_market_status(_tadawul(2026, 7, 28, 9, 45))
        assert info.status == MarketSessionStatus.PRE_OPEN_AUCTION
        assert info.label_ar == "مزاد الافتتاح"
        assert info.seconds_until_close is None

    def test_closing_auction(self):
        info = get_market_status(_tadawul(2026, 7, 28, 15, 5))
        assert info.status == MarketSessionStatus.CLOSING_AUCTION
        assert info.label_ar == "مزاد الإغلاق"

    def test_post_close_after_hours(self):
        info = get_market_status(_tadawul(2026, 7, 28, 20, 0))
        assert info.status == MarketSessionStatus.POST_CLOSE
        assert info.label_ar == "بعد الإغلاق"

    def test_pre_market_before_pre_open(self):
        info = get_market_status(_tadawul(2026, 7, 28, 6, 0))
        assert info.status == MarketSessionStatus.PRE_MARKET
        assert info.label_ar == "قبل الافتتاح"

    def test_closing_price_trading(self):
        info = get_market_status(_tadawul(2026, 7, 28, 15, 15))
        assert info.status == MarketSessionStatus.CLOSING_PRICE_TRADING
        assert info.label_ar == "التداول على سعر الإغلاق"

    def test_weekend_on_friday(self):
        info = get_market_status(_tadawul(2026, 7, 31, 12, 0))
        assert info.status == MarketSessionStatus.WEEKEND
        assert info.label_ar == "عطلة أسبوعية"
        assert info.is_trading_day is False

    def test_last_completed_session_on_a_trading_day_before_open(self):
        # Tuesday 09:00, before that day's own close -- last completed
        # session is the prior trading day (Monday).
        info = get_market_status(_tadawul(2026, 7, 28, 9, 0))
        assert info.last_completed_session_date.isoformat() == "2026-07-27"

    def test_last_completed_session_on_a_trading_day_after_close(self):
        info = get_market_status(_tadawul(2026, 7, 28, 20, 0))
        assert info.last_completed_session_date.isoformat() == "2026-07-28"

    def test_last_completed_session_on_friday_is_thursday(self):
        info = get_market_status(_tadawul(2026, 7, 31, 12, 0))
        assert info.last_completed_session_date.isoformat() == "2026-07-30"

    def test_disclosed_gap_note_is_always_present(self):
        info = get_market_status(_tadawul(2026, 7, 28, 12, 0))
        assert "عطلة" in info.holiday_calendar_disclosed_gap
