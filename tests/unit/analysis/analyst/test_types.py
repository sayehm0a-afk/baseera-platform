"""Unit tests for src/analysis/analyst/types.py -- Evidence's derived
availability properties are the only non-trivial logic in this module
(everything else is plain dataclass field storage)."""

from tests.unit.analysis.analyst._fixtures import make_evidence


def test_evidence_reports_technical_unavailable_when_none():
    evidence = make_evidence(technical_result=None)
    assert evidence.technical_available is False


def test_evidence_reports_technical_available_when_present():
    evidence = make_evidence(technical_result=object())
    assert evidence.technical_available is True


def test_evidence_reports_fundamental_unavailable_when_none():
    evidence = make_evidence(fundamental_result=None)
    assert evidence.fundamental_available is False


def test_evidence_reports_fundamental_available_when_present():
    evidence = make_evidence(fundamental_result=object())
    assert evidence.fundamental_available is True
