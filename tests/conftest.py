"""Root-level fixtures shared by every test under tests/ -- pytest
auto-applies a conftest.py to every test file below it in the
directory tree, so this file's fixtures need no explicit import
anywhere.
"""

import pytest

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
