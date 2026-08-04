"""Unit tests for scripts/verify_sahmk_historical_deep_dive.py's pure
key-resolution logic (`_find_key`). Local only, no network -- the one
real, unmocked verification lives in the script itself, run only by
.github/workflows/sahmk-live-verification.yml on manual dispatch.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import pytest  # noqa: E402

from scripts.verify_sahmk_historical_deep_dive import _find_key  # noqa: E402


class TestFindKey:
    def test_returns_first_matching_candidate(self):
        bar = {"close": 26.5, "open": 26.0}
        assert _find_key(bar, ["close", "c"]) == "close"

    def test_falls_through_to_later_candidate(self):
        bar = {"c": 26.5}
        assert _find_key(bar, ["close", "c"]) == "c"

    def test_raises_key_error_when_no_candidate_present(self):
        bar = {"unrelated": 1}
        with pytest.raises(KeyError):
            _find_key(bar, ["close", "c"])
