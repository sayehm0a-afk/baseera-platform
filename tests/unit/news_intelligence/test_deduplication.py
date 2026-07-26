"""Unit tests for src.news_intelligence.deduplication -- pure
functions, no network, no database."""

from datetime import datetime, timezone

from src.news_intelligence.deduplication import external_key, find_duplicate, headline_similarity, normalize_headline
from src.news_intelligence.types import CanonicalCandidate, RawNewsItem


def test_normalize_headline_collapses_whitespace_and_case():
    assert normalize_headline("  Saudi   Aramco  Reports  Profit  ") == "saudi aramco reports profit"


def test_external_key_is_deterministic_for_the_same_inputs():
    ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
    key_a = external_key("sahmk", "Aramco reports profit", ts)
    key_b = external_key("sahmk", "Aramco reports profit", ts)
    assert key_a == key_b


def test_external_key_differs_when_source_differs():
    ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert external_key("sahmk", "Aramco reports profit", ts) != external_key("argaam", "Aramco reports profit", ts)


def test_external_key_is_insensitive_to_whitespace_and_case_in_headline():
    ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
    key_a = external_key("sahmk", "Aramco Reports Profit", ts)
    key_b = external_key("sahmk", "  aramco   reports   profit  ", ts)
    assert key_a == key_b


def test_headline_similarity_identical_is_one():
    assert headline_similarity("Aramco reports record profit", "Aramco reports record profit") == 1.0


def test_headline_similarity_unrelated_is_low():
    assert headline_similarity("Aramco reports record profit", "SABIC announces new plant") < 0.5


def test_find_duplicate_matches_near_identical_headline():
    item = RawNewsItem(headline="Saudi Aramco reports record quarterly profit", source="argaam", is_synthetic=False)
    candidates = [CanonicalCandidate(id=1, headline="Saudi Aramco reports record quarterly profit")]
    result = find_duplicate(item, candidates)
    assert result.is_duplicate is True
    assert result.canonical_event_id == 1
    assert result.similarity == 1.0


def test_find_duplicate_does_not_match_a_distinct_story_about_the_same_company():
    item = RawNewsItem(headline="Saudi Aramco announces new CEO", source="sahmk", is_synthetic=False)
    candidates = [CanonicalCandidate(id=1, headline="Saudi Aramco reports record quarterly profit")]
    result = find_duplicate(item, candidates)
    assert result.is_duplicate is False
    assert result.canonical_event_id is None


def test_find_duplicate_returns_the_best_match_among_several_candidates():
    item = RawNewsItem(headline="Saudi Aramco reports record quarterly profit for Q2", source="argaam", is_synthetic=False)
    candidates = [
        CanonicalCandidate(id=1, headline="SABIC announces expansion"),
        CanonicalCandidate(id=2, headline="Saudi Aramco reports record quarterly profit"),
    ]
    result = find_duplicate(item, candidates)
    assert result.canonical_event_id == 2


def test_find_duplicate_respects_a_custom_threshold():
    item = RawNewsItem(headline="Aramco Q2 profit up", source="argaam", is_synthetic=False)
    candidates = [CanonicalCandidate(id=1, headline="Saudi Aramco reports record quarterly profit")]
    lenient = find_duplicate(item, candidates, threshold=0.1)
    strict = find_duplicate(item, candidates, threshold=0.99)
    assert lenient.is_duplicate is True
    assert strict.is_duplicate is False


def test_find_duplicate_with_no_candidates_is_never_a_duplicate():
    item = RawNewsItem(headline="Anything", source="sahmk", is_synthetic=False)
    result = find_duplicate(item, [])
    assert result.is_duplicate is False
