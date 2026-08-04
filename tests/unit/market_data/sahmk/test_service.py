"""Unit tests for SahmkMarketDataService -- SahmkClient is mocked
directly, no network involved."""

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock

import pytest

from src.market_data.sahmk.exceptions import SahmkResponseValidationError
from src.market_data.sahmk.models import (
    SahmkCompanyProfile,
    SahmkDividend,
    SahmkEvent,
    SahmkHistoricalBar,
    SahmkMarketSummary,
    SahmkQuote,
)
from src.market_data.sahmk.service import SahmkMarketDataService


def _service(client=None):
    return SahmkMarketDataService(client=client or AsyncMock())


# --- get_latest_quote ------------------------------------------------------


@pytest.mark.asyncio
async def test_get_latest_quote_parses_full_response():
    client = AsyncMock()
    client.get_quote.return_value = {
        "price": 42.5,
        "change": 1.2,
        "change_percent": 2.9,
        "volume": 1000,
        "updated_at": "2026-01-05T12:00:00Z",
    }
    service = _service(client)
    quote = await service.get_latest_quote("1120")
    assert quote == SahmkQuote(
        symbol="1120",
        price=42.5,
        change=1.2,
        change_percent=2.9,
        volume=1000,
        timestamp=datetime(2026, 1, 5, 12, 0, tzinfo=timezone.utc),
    )


@pytest.mark.asyncio
async def test_get_latest_quote_tolerates_missing_optional_fields():
    client = AsyncMock()
    client.get_quote.return_value = {"price": 10.0}
    service = _service(client)
    quote = await service.get_latest_quote("1120")
    assert quote.price == 10.0
    assert quote.change is None
    assert quote.volume is None


@pytest.mark.asyncio
async def test_get_latest_quote_raises_when_price_missing():
    client = AsyncMock()
    client.get_quote.return_value = {"volume": 100}
    service = _service(client)
    with pytest.raises(SahmkResponseValidationError):
        await service.get_latest_quote("1120")


@pytest.mark.asyncio
async def test_get_latest_quote_is_cached():
    client = AsyncMock()
    client.get_quote.return_value = {"price": 1.0}
    service = _service(client)
    await service.get_latest_quote("1120")
    await service.get_latest_quote("1120")
    client.get_quote.assert_awaited_once_with("1120")


@pytest.mark.asyncio
async def test_get_latest_quote_reads_updated_at_not_timestamp():
    """Regression test: the real SAHMK /quote/ response has no
    "timestamp" field -- confirmed live 2026-07-27 (run 30302024204) --
    only "updated_at". A response carrying an unrelated "timestamp" key
    alongside the real "updated_at" must not be misread."""
    client = AsyncMock()
    client.get_quote.return_value = {
        "price": 26.56,
        "updated_at": "2026-07-27T12:19:08+00:00",
        "timestamp": "2099-01-01T00:00:00Z",  # decoy: must be ignored
    }
    service = _service(client)
    quote = await service.get_latest_quote("2222")
    assert quote.timestamp == datetime(2026, 7, 27, 12, 19, 8, tzinfo=timezone.utc)


# --- get_historical_bars / get_daily_bar ------------------------------------


@pytest.mark.asyncio
async def test_get_historical_bars_parses_every_bar():
    client = AsyncMock()
    client.get_historical.return_value = {
        "data": [
            {"open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 10, "date": "2026-01-05"},
            {"open": 2, "high": 3, "low": 1.5, "close": 2.5, "volume": 20, "date": "2026-01-06"},
        ]
    }
    service = _service(client)
    bars = await service.get_historical_bars("1120", date(2026, 1, 5), date(2026, 1, 6))
    assert bars == [
        SahmkHistoricalBar("1120", 1.0, 2.0, 0.5, 1.5, 10, datetime(2026, 1, 5, tzinfo=timezone.utc)),
        SahmkHistoricalBar("1120", 2.0, 3.0, 1.5, 2.5, 20, datetime(2026, 1, 6, tzinfo=timezone.utc)),
    ]


@pytest.mark.asyncio
async def test_get_historical_bars_reads_the_data_key_not_bars():
    """Regression test: the real SAHMK /historical/ response has no
    top-level "bars" key -- confirmed live 2026-07-27 (run 30303216761,
    118 real daily bars for symbol 2222) -- the array is under "data".
    A response carrying a decoy "bars" key must not be read instead."""
    client = AsyncMock()
    client.get_historical.return_value = {
        "data": [{"open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 10, "date": "2026-01-05"}],
        "bars": [{"open": 999, "high": 999, "low": 999, "close": 999, "volume": 999, "date": "2099-01-01"}],
    }
    service = _service(client)
    bars = await service.get_historical_bars("1120", date(2026, 1, 5), date(2026, 1, 5))
    assert len(bars) == 1
    assert bars[0].close == 1.5


@pytest.mark.asyncio
async def test_get_historical_bars_raises_on_bar_missing_required_field():
    client = AsyncMock()
    client.get_historical.return_value = {"data": [{"open": 1, "close": 1.5}]}
    service = _service(client)
    with pytest.raises(SahmkResponseValidationError):
        await service.get_historical_bars("1120", date(2026, 1, 5), date(2026, 1, 5))


@pytest.mark.asyncio
async def test_get_daily_bar_returns_last_bar():
    client = AsyncMock()
    client.get_historical.return_value = {
        "data": [
            {"open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 10, "date": "2026-01-05"},
            {"open": 2, "high": 3, "low": 1.5, "close": 2.9, "volume": 20, "date": "2026-01-06"},
        ]
    }
    service = _service(client)
    bar = await service.get_daily_bar("1120", on=date(2026, 1, 5))
    assert bar.close == 2.9


@pytest.mark.asyncio
async def test_get_daily_bar_raises_when_no_bars_returned():
    client = AsyncMock()
    client.get_historical.return_value = {"data": []}
    service = _service(client)
    with pytest.raises(SahmkResponseValidationError):
        await service.get_daily_bar("1120", on=date(2026, 1, 5))


# --- get_index_snapshot ------------------------------------------------------


@pytest.mark.asyncio
async def test_get_index_snapshot_parses_response():
    client = AsyncMock()
    client.get_market_summary.return_value = {
        "index_value": 12000.5,
        "index_change": 50.0,
        "index_change_percent": 0.42,
        "timestamp": "2026-01-05T15:00:00Z",
    }
    service = _service(client)
    summary = await service.get_index_snapshot("TASI")
    assert summary == SahmkMarketSummary(
        index="TASI",
        value=12000.5,
        change=50.0,
        change_percent=0.42,
        timestamp=datetime(2026, 1, 5, 15, 0, tzinfo=timezone.utc),
    )


@pytest.mark.asyncio
async def test_get_index_snapshot_raises_when_index_value_missing():
    client = AsyncMock()
    client.get_market_summary.return_value = {}
    service = _service(client)
    with pytest.raises(SahmkResponseValidationError):
        await service.get_index_snapshot("TASI")


# --- get_recent_events --------------------------------------------------


@pytest.mark.asyncio
async def test_get_recent_events_parses_events_key():
    client = AsyncMock()
    client.get_events.return_value = {
        "events": [{"symbol": "1120", "headline": "Big news", "timestamp": "2026-01-05T00:00:00Z"}]
    }
    service = _service(client)
    events = await service.get_recent_events(limit=1)
    assert events == [
        SahmkEvent(
            symbol="1120",
            headline="Big news",
            timestamp=datetime(2026, 1, 5, tzinfo=timezone.utc),
            raw={"symbol": "1120", "headline": "Big news", "timestamp": "2026-01-05T00:00:00Z"},
        )
    ]


@pytest.mark.asyncio
async def test_get_recent_events_falls_back_to_results_key_and_title_field():
    client = AsyncMock()
    client.get_events.return_value = {"results": [{"title": "Fallback headline"}]}
    service = _service(client)
    events = await service.get_recent_events(limit=1)
    assert events[0].headline == "Fallback headline"
    assert events[0].symbol is None


# --- get_company_profile ------------------------------------------------------


@pytest.mark.asyncio
async def test_get_company_profile_parses_known_field_names():
    client = AsyncMock()
    client.get_company_profile.return_value = {
        "name": "Saudi Aramco", "sector": "Energy", "industry": "Oil & Gas", "exchange": "Tadawul",
    }
    service = _service(client)
    profile = await service.get_company_profile("2222")
    assert profile == SahmkCompanyProfile(
        symbol="2222",
        name="Saudi Aramco",
        sector="Energy",
        industry="Oil & Gas",
        exchange="Tadawul",
        raw={"name": "Saudi Aramco", "sector": "Energy", "industry": "Oil & Gas", "exchange": "Tadawul"},
    )


@pytest.mark.asyncio
async def test_get_company_profile_tolerates_missing_fields():
    client = AsyncMock()
    client.get_company_profile.return_value = {}
    service = _service(client)
    profile = await service.get_company_profile("2222")
    assert profile.name is None
    assert profile.sector is None
    assert profile.industry is None
    assert profile.exchange is None


# --- get_company_directory -------------------------------------------------


@pytest.mark.asyncio
async def test_get_company_directory_parses_companies_key():
    client = AsyncMock()
    client.get_companies.return_value = {
        "companies": [
            {"symbol": "2222", "name": "Saudi Aramco", "sector": "Energy"},
            {"symbol": "1120", "name": "Al Rajhi Bank", "sector": "Financials"},
        ]
    }
    service = _service(client)
    directory = await service.get_company_directory()
    assert [c.symbol for c in directory] == ["2222", "1120"]
    assert directory[0].name == "Saudi Aramco"
    assert directory[0].sector == "Energy"


@pytest.mark.asyncio
async def test_get_company_directory_falls_back_to_results_and_ticker_key():
    client = AsyncMock()
    client.get_companies.return_value = {"results": [{"ticker": "2010", "company_name": "SABIC"}]}
    service = _service(client)
    directory = await service.get_company_directory()
    assert directory[0].symbol == "2010"
    assert directory[0].name == "SABIC"


@pytest.mark.asyncio
async def test_get_company_directory_skips_entries_with_no_symbol():
    client = AsyncMock()
    client.get_companies.return_value = {"companies": [{"name": "No Symbol Co"}]}
    service = _service(client)
    directory = await service.get_company_directory()
    assert directory == []


@pytest.mark.asyncio
async def test_get_company_directory_is_cached():
    client = AsyncMock()
    client.get_companies.return_value = {"companies": [{"symbol": "2222"}]}
    service = _service(client)
    await service.get_company_directory()
    await service.get_company_directory()
    client.get_companies.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_company_directory_no_pagination_signal_is_not_verified():
    """A single-page response with no next/count/total field at all --
    the previously-silent case (two real full-universe runs both
    returned exactly 100 companies this way) -- must now be an
    explicit, honest UNIVERSE_NOT_VERIFIED, never assumed complete."""
    client = AsyncMock()
    client.get_companies.return_value = {"companies": [{"symbol": "1010"}, {"symbol": "1020"}]}
    service = _service(client)
    directory = await service.get_company_directory()
    assert len(directory) == 2
    client.get_companies.assert_awaited_once()
    diag = service.last_directory_diagnostics
    assert diag.universe_verdict == "UNIVERSE_NOT_VERIFIED"
    assert diag.pages_fetched == 1
    assert diag.reported_total is None


@pytest.mark.asyncio
async def test_get_company_directory_follows_next_url_pagination():
    client = AsyncMock()
    client.get_companies.side_effect = [
        {
            "companies": [{"symbol": "1010"}, {"symbol": "1020"}],
            "next": "https://app.sahmk.sa/api/v1/companies/?page=2",
        },
        {"companies": [{"symbol": "1030"}], "next": None},
    ]
    service = _service(client)
    directory = await service.get_company_directory()
    assert [c.symbol for c in directory] == ["1010", "1020", "1030"]
    assert client.get_companies.await_count == 2
    second_call_kwargs = client.get_companies.await_args_list[1].kwargs
    assert second_call_kwargs["params"] == {"page": "2"}
    diag = service.last_directory_diagnostics
    assert diag.pagination_signal == "next_url"
    assert diag.pages_fetched == 2
    assert diag.universe_verdict == "PARTIAL_UNIVERSE_VERIFIED"


@pytest.mark.asyncio
async def test_get_company_directory_follows_count_total_pagination_to_full_verification():
    client = AsyncMock()
    client.get_companies.side_effect = [
        {"companies": [{"symbol": "1010"}, {"symbol": "1020"}], "count": 3},
        {"companies": [{"symbol": "1030"}], "count": 3},
    ]
    service = _service(client)
    directory = await service.get_company_directory()
    assert [c.symbol for c in directory] == ["1010", "1020", "1030"]
    diag = service.last_directory_diagnostics
    assert diag.pagination_signal == "count_total"
    assert diag.reported_total == 3
    assert diag.universe_verdict == "FULL_UNIVERSE_VERIFIED"


@pytest.mark.asyncio
async def test_get_company_directory_partial_when_total_never_reconciled():
    """The server claims more records exist (count=500) but the same
    company keeps coming back (a broken/looping page param) -- must
    report PARTIAL, never FULL, and must stop as soon as a page adds
    no new companies rather than looping to _MAX_DIRECTORY_PAGES."""
    client = AsyncMock()
    client.get_companies.return_value = {"companies": [{"symbol": "1010"}], "count": 500}
    service = _service(client)
    directory = await service.get_company_directory()
    assert len(directory) == 1
    diag = service.last_directory_diagnostics
    assert diag.universe_verdict == "PARTIAL_UNIVERSE_VERIFIED"
    # Page 1 fetches the only real company; page 2 (same mocked
    # response) contributes zero *new* companies, so the loop stops
    # there instead of continuing to _MAX_DIRECTORY_PAGES.
    assert diag.pages_fetched == 2


@pytest.mark.asyncio
async def test_get_company_directory_pagination_is_bounded():
    """A response that always claims more records than it delivers
    (each page returns exactly one *new* company, forever) must stop
    at _MAX_DIRECTORY_PAGES, never spin unbounded."""
    call_count = {"n": 0}

    async def _fake_get_companies(params=None):
        call_count["n"] += 1
        n = call_count["n"]
        return {"companies": [{"symbol": f"S{n}"}], "count": 10_000}

    client = AsyncMock()
    client.get_companies.side_effect = _fake_get_companies
    service = _service(client)
    directory = await service.get_company_directory()
    from src.market_data.sahmk import service as service_module

    assert len(directory) == service_module._MAX_DIRECTORY_PAGES
    assert call_count["n"] == service_module._MAX_DIRECTORY_PAGES
    assert service.last_directory_diagnostics.universe_verdict == "PARTIAL_UNIVERSE_VERIFIED"


@pytest.mark.asyncio
async def test_get_company_directory_deduplicates_across_pages():
    client = AsyncMock()
    client.get_companies.side_effect = [
        {"companies": [{"symbol": "1010"}], "next": "https://x/?page=2"},
        {"companies": [{"symbol": "1010"}], "next": None},  # same symbol repeated
    ]
    service = _service(client)
    directory = await service.get_company_directory()
    assert [c.symbol for c in directory] == ["1010"]


@pytest.mark.asyncio
async def test_get_company_directory_extracts_nested_sector_object():
    client = AsyncMock()
    client.get_companies.return_value = {
        "companies": [{"symbol": "2222", "sector": {"name": "Energy"}}]
    }
    service = _service(client)
    directory = await service.get_company_directory()
    assert directory[0].sector == "Energy"


@pytest.mark.asyncio
async def test_get_company_directory_records_diagnostics_when_sector_unresolved():
    client = AsyncMock()
    client.get_companies.return_value = {
        "companies": [{"symbol": "1010", "gics_industry_group": "Banks"}]
    }
    service = _service(client)
    directory = await service.get_company_directory()
    assert directory[0].sector is None
    diag = service.last_directory_diagnostics
    assert diag.sector_populated_count == 0
    assert "gics_industry_group" in diag.first_item_keys


# --- get_financials ------------------------------------------------------


@pytest.mark.asyncio
async def test_get_financials_parses_primary_field_names():
    client = AsyncMock()
    client.get_financials.return_value = {
        "fiscal_period_end": "2025-12-31",
        "revenue": 100.0,
        "net_income": 20.0,
        "total_assets": 500.0,
        "total_liabilities": 200.0,
        "total_equity": 300.0,
        "current_assets": 150.0,
        "current_liabilities": 80.0,
        "shares_outstanding": 1000,
        "eps": 0.02,
    }
    service = _service(client)
    financials = await service.get_financials("2222", period_type="annual")
    assert financials.revenue == 100.0
    assert financials.net_income == 20.0
    assert financials.shares_outstanding == 1000
    assert financials.eps == 0.02
    assert financials.period_type == "annual"
    client.get_financials.assert_awaited_once_with("2222", period_type="annual")


@pytest.mark.asyncio
async def test_get_financials_falls_back_to_alternate_field_names():
    client = AsyncMock()
    client.get_financials.return_value = {
        "period_end": "2025-12-31",
        "total_revenue": 100.0,
        "net_profit": 20.0,
        "shareholders_equity": 300.0,
        "shares": 1000,
        "earnings_per_share": 0.02,
    }
    service = _service(client)
    financials = await service.get_financials("2222")
    assert financials.fiscal_period_end == "2025-12-31"
    assert financials.revenue == 100.0
    assert financials.net_income == 20.0
    assert financials.total_equity == 300.0
    assert financials.shares_outstanding == 1000
    assert financials.eps == 0.02


@pytest.mark.asyncio
async def test_get_financials_never_raises_on_missing_fields_and_keeps_raw():
    client = AsyncMock()
    client.get_financials.return_value = {"unexpected_field": "x"}
    service = _service(client)
    financials = await service.get_financials("2222")
    assert financials.revenue is None
    assert financials.raw == {"unexpected_field": "x"}


@pytest.mark.asyncio
async def test_get_financials_is_cached_per_symbol_and_period():
    client = AsyncMock()
    client.get_financials.return_value = {"revenue": 1}
    service = _service(client)
    await service.get_financials("2222", period_type="annual")
    await service.get_financials("2222", period_type="annual")
    client.get_financials.assert_awaited_once()


# The real, live-captured shape of GET /financials/{symbol}/ (workflow
# run 30436660246, symbol 1120) -- three separate per-period statement
# arrays, most-recent period first. current_assets/current_liabilities/
# shares_outstanding/eps are absent everywhere in this real response,
# confirmed for 3 real symbols, not a parsing gap.
_REAL_FINANCIALS_RESPONSE = {
    "symbol": "1120",
    "statement_period": "annual",
    "income_statements": [
        {
            "report_date": "2025-12-31", "statement_period": "annual", "fiscal_year": 2025,
            "quarters_reported": 4, "is_full_year": True,
            "total_revenue": 39093965000.0, "gross_profit": 6730335.0,
            "operating_income": None, "net_income": 24791754000.0,
        },
        {
            "report_date": "2024-12-31", "statement_period": "annual", "fiscal_year": 2024,
            "quarters_reported": 4, "is_full_year": True,
            "total_revenue": 52742285000.0, "gross_profit": 10989066000.0,
            "operating_income": None, "net_income": 19722206000.0,
        },
    ],
    "balance_sheets": [
        {
            "report_date": "2025-12-31", "statement_period": "annual", "fiscal_year": 2025,
            "quarters_reported": 4, "is_full_year": True,
            "total_assets": 1043268297000.0, "total_liabilities": 900355952000.0,
            "stockholders_equity": 142912345000.0, "total_debt": 80320898000.0,
        },
        {
            "report_date": "2024-12-31", "statement_period": "annual", "fiscal_year": 2024,
            "quarters_reported": 4, "is_full_year": True,
            "total_assets": 974386656000.0, "total_liabilities": 851247425000.0,
            "stockholders_equity": 123139231000.0, "total_debt": 37943190000.0,
        },
    ],
    "cash_flows": [
        {
            "report_date": "2025-12-31", "statement_period": "annual", "fiscal_year": 2025,
            "quarters_reported": 4, "is_full_year": True,
            "operating_cash_flow": -22373072000.0, "investing_cash_flow": -1564467000.0,
            "financing_cash_flow": 36302349000.0, "free_cash_flow": -50224247000.0,
        },
    ],
}


@pytest.mark.asyncio
async def test_get_financials_parses_the_real_nested_statement_shape():
    client = AsyncMock()
    client.get_financials.return_value = _REAL_FINANCIALS_RESPONSE
    service = _service(client)
    financials = await service.get_financials("1120", period_type="annual")

    assert financials.fiscal_period_end == "2025-12-31"
    assert financials.revenue == 39093965000.0
    assert financials.gross_profit == 6730335.0
    assert financials.net_income == 24791754000.0
    assert financials.total_assets == 1043268297000.0
    assert financials.total_liabilities == 900355952000.0
    assert financials.total_equity == 142912345000.0
    assert financials.total_debt == 80320898000.0


@pytest.mark.asyncio
async def test_get_financials_real_response_never_has_these_fields():
    # Genuine data-source gap, confirmed live -- not a parsing bug.
    client = AsyncMock()
    client.get_financials.return_value = _REAL_FINANCIALS_RESPONSE
    service = _service(client)
    financials = await service.get_financials("1120", period_type="annual")

    assert financials.current_assets is None
    assert financials.current_liabilities is None
    assert financials.shares_outstanding is None
    assert financials.eps is None
    assert financials.inventory is None
    assert financials.cash_and_equivalents is None


@pytest.mark.asyncio
async def test_get_financials_picks_statement_matching_requested_period_type():
    client = AsyncMock()
    client.get_financials.return_value = {
        "income_statements": [
            {"report_date": "2025-Q4", "statement_period": "quarterly", "total_revenue": 1.0, "net_income": 1.0},
            {"report_date": "2025-12-31", "statement_period": "annual", "total_revenue": 999.0, "net_income": 100.0},
        ],
        "balance_sheets": [],
    }
    service = _service(client)
    financials = await service.get_financials("1120", period_type="annual")
    assert financials.revenue == 999.0
    assert financials.net_income == 100.0


# --- get_dividends / get_latest_dividend_per_share ------------------------


@pytest.mark.asyncio
async def test_get_dividends_parses_dividends_key():
    first = {"dividend_per_share": 1.5, "ex_date": "2025-06-01", "payment_date": "2025-07-01"}
    second = {"dividend_per_share": 1.2, "ex_date": "2024-06-01", "payment_date": "2024-07-01"}
    client = AsyncMock()
    client.get_dividends.return_value = {"dividends": [first, second]}
    service = _service(client)
    dividends = await service.get_dividends("2222")
    assert dividends == [
        SahmkDividend("2222", 1.5, "2025-06-01", "2025-07-01", first),
        SahmkDividend("2222", 1.2, "2024-06-01", "2024-07-01", second),
    ]


@pytest.mark.asyncio
async def test_get_dividends_falls_back_to_results_and_amount_field():
    client = AsyncMock()
    client.get_dividends.return_value = {"results": [{"amount": 2.0}]}
    service = _service(client)
    dividends = await service.get_dividends("2222")
    assert dividends[0].dividend_per_share == 2.0


@pytest.mark.asyncio
async def test_get_dividends_skips_entries_with_no_amount():
    client = AsyncMock()
    client.get_dividends.return_value = {"dividends": [{"ex_date": "2025-01-01"}]}
    service = _service(client)
    dividends = await service.get_dividends("2222")
    assert dividends == []


@pytest.mark.asyncio
async def test_get_latest_dividend_per_share_returns_most_recent():
    client = AsyncMock()
    client.get_dividends.return_value = {"dividends": [{"dividend_per_share": 1.5}]}
    service = _service(client)
    assert await service.get_latest_dividend_per_share("2222") == 1.5


@pytest.mark.asyncio
async def test_get_latest_dividend_per_share_none_when_no_history():
    client = AsyncMock()
    client.get_dividends.return_value = {"dividends": []}
    service = _service(client)
    assert await service.get_latest_dividend_per_share("2222") is None


# --- check_health ------------------------------------------------------


@pytest.mark.asyncio
async def test_check_health_true_on_success():
    client = AsyncMock()
    client.get_market_summary.return_value = {"index_value": 1}
    service = _service(client)
    assert await service.check_health() is True


@pytest.mark.asyncio
async def test_check_health_false_on_any_failure():
    client = AsyncMock()
    client.get_market_summary.side_effect = RuntimeError("boom")
    service = _service(client)
    assert await service.check_health() is False


@pytest.mark.asyncio
async def test_close_delegates_to_client():
    client = AsyncMock()
    service = _service(client)
    await service.close()
    client.close.assert_awaited_once()


def test_has_credentials_delegates_to_client():
    client = AsyncMock()
    client.has_credentials = True
    service = _service(client)
    assert service.has_credentials is True
