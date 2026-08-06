"""Tests for decision_v2/types.py's shared persistence-boundary helpers
-- sub_scores_to_dict/gates_to_dicts, the one place both /decision-v2's
route and the market scan pipeline flatten a DecisionResult into the
plain dict/list that reaches a JSON column.
"""

import numpy as np

from src.analysis.decision_v2.types import GateOutcome, GateStatus, SubScores, gates_to_dicts, sub_scores_to_dict


def test_sub_scores_to_dict_coerces_numpy_floats_to_plain_floats():
    """Regression: src.analysis.indicators computations are numpy-
    backed, so sub-score inputs can carry numpy.float64. json.dumps
    accepts a plain float but not numpy.float64 -- this must never
    reach the sub_scores JSON column un-coerced (confirmed in
    production: a real scan run failed with "Object of type bool is
    not JSON serializable" once numpy scalars reached this boundary)."""
    sub_scores = SubScores(
        trend_score=np.float64(61.2),
        momentum_score=np.float64(57.4),
        volume_score=None,
        liquidity_score=np.float64(80.0),
        volatility_score=None,
        risk_reward_score=np.float64(64.75),
        market_context_score=np.float64(75.0),
        data_quality_score=np.float64(100.0),
    )

    result = sub_scores_to_dict(sub_scores)

    assert result["volume_score"] is None
    for field, value in result.items():
        if value is not None:
            assert type(value) is float, f"{field} was {type(value)!r}, expected plain float"


def test_gates_to_dicts_coerces_numpy_bool_to_plain_bool():
    """Regression: a gate's `passed`/`blocking` can be the result of a
    comparison against a numpy-typed threshold (e.g. `price > numpy_atr`),
    which yields numpy.bool_ -- not JSON serializable by the stdlib
    encoder even though it prints identically to a plain bool."""
    gates = [GateOutcome(name="real_data_source", status=GateStatus.PASS, detail="ok", blocking=np.bool_(False))]

    result = gates_to_dicts(gates)

    assert result == [
        {"name": "real_data_source", "status": "PASS", "passed": True, "detail": "ok", "blocking": False}
    ]
    assert type(result[0]["passed"]) is bool
    assert type(result[0]["blocking"]) is bool
