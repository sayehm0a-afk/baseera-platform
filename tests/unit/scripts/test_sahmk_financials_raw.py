"""Unit tests for scripts/verify_sahmk_financials_raw.py's pure
`_describe_shape` structural summarizer. Local only, no network -- the
one real, unmocked call lives in the script itself, run only by a
GitHub Actions manual dispatch.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from scripts.verify_sahmk_financials_raw import _describe_shape  # noqa: E402


class TestDescribeShape:
    def test_flat_dict(self):
        assert _describe_shape({"revenue": 100, "name": "x"}) == {"revenue": "int", "name": "str"}

    def test_nested_dict_is_recursed(self):
        shape = _describe_shape({"balance_sheet": {"total_assets": 100.0}})
        assert shape == {"balance_sheet": {"total_assets": "float"}}

    def test_list_reports_length_and_first_item_shape(self):
        shape = _describe_shape({"statements": [{"revenue": 1}, {"revenue": 2}]})
        assert shape == {"statements": ["list[2] of ->", {"revenue": "int"}]}

    def test_empty_list_reported_without_recursing(self):
        assert _describe_shape({"statements": []}) == {"statements": "list[empty]"}

    def test_depth_cap_stops_recursion(self):
        deeply_nested = {"a": {"b": {"c": {"d": "too deep"}}}}
        shape = _describe_shape(deeply_nested, max_depth=2)
        assert shape == {"a": {"b": "dict"}}
