"""Root-level fixtures shared by every test under tests/ -- pytest
auto-applies a conftest.py to every test file below it in the
directory tree, so this file's fixtures need no explicit import
anywhere.
"""

import pytest

from src.api.middleware.rate_limiting import limiter
from src.api.routes.stocks import _directory_search_cache
from src.market_intelligence.sector_reliability import _sector_reliability_cache


@pytest.fixture(autouse=True)
def _reset_sector_reliability_cache():
    """`compute_sector_reliability_by_arabic_label` (2026-09-19 audit
    fix) is now wrapped in a module-level, process-lifetime `TTLCache`
    (see src/market_intelligence/sector_reliability.py) -- correct for
    production (a market-wide aggregate, safely stale for a few
    minutes), but without this reset a value cached by one test would
    leak into the next test in the same pytest process, since every
    test's in-memory-sqlite `RecommendationOutcome` data differs while
    the cache key (`evaluation_horizon_days`) usually does not."""
    _sector_reliability_cache.clear()
    yield
    _sector_reliability_cache.clear()


@pytest.fixture(autouse=True)
def _reset_directory_search_cache():
    """Same leakage risk as `_reset_sector_reliability_cache` above,
    for `GET /stocks/directory`'s `q`-branch cache (2026-09-19 perf
    fix, see src/api/routes/stocks.py's `_directory_search_cache`):
    every test's in-memory-sqlite `Stock` rows differ while the cache
    key (`query`, `sector`) can easily repeat across tests (e.g. many
    tests search for the same symbol/sector), so without this reset a
    match list cached by one test could be served, wrong, to the next."""
    _directory_search_cache.clear()
    yield
    _directory_search_cache.clear()


@pytest.fixture(autouse=True)
def _reset_rate_limiter_storage():
    """`limiter` (src/api/middleware/rate_limiting.py) is Redis-backed
    so its budget is consistent across gunicorn workers in production
    -- but that same shared, process-external storage means every
    call any test makes to a `@limiter.limit(...)`-decorated route
    accumulates against the same real Redis keys across the whole
    pytest session (get_remote_address always returns the same
    TestClient IP), not per-test. Without this reset, a route-heavy
    test file exercising a real limit dozens of times (e.g.
    test_backtests_routes.py's ~29 POSTs) would start hitting 429s
    partway through on tests that have nothing to do with rate
    limiting."""
    limiter.reset()
    yield
    limiter.reset()
