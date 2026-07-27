"""Pure classification logic for the SAHMK live-verification diagnostic
script (scripts/verify_sahmk_live.py).

Deliberately separated from the script that actually talks to the
network: everything in this module is a pure function/dataclass over
already-observed outcomes (an HTTP status code, whether a network
exception was raised, whether required fields were present) -- never
performs I/O itself. That is what makes it possible to unit-test the
full decision tree with local sample status codes (tests/unit/scripts/
test_sahmk_live_diagnosis.py) while keeping the one real, unmocked
network call inside the script, exactly as required: "keep the GitHub
workflow itself as the real unmocked verification."

Decision tree, in one place, in execution order:

  Layer A (DNS/TLS reachability to app.sahmk.sa)
    fails -> SAHMK_NETWORK_BLOCKED, stop.

  Layer B (GET /quote/2222/ with X-API-Key, no Basirah code involved)
    network/timeout error       -> SAHMK_NETWORK_BLOCKED, stop.
    401                          -> SAHMK_KEY_INVALID, stop.
    403                          -> SAHMK_PLAN_RESTRICTION, stop.
    429 / 5xx / malformed 200    -> INCONCLUSIVE, stop. (see note below)
    200 with usable fields       -> proceed to Layer C.

  Layer C (real SahmkClient.get_quote, then real
           SahmkMarketDataService.get_latest_quote -- same symbol)
    SahmkClient itself raises unexpectedly (Layer B's raw call already
    proved the direct API works) -> BASIRAH_CLIENT_BROKEN, stop.
    SahmkMarketDataService's parsing/validation raises
                                  -> BASIRAH_PARSER_MISMATCH, stop.
    not run (should not happen if Layer B was OK, defensive only)
                                  -> SAHMK_CONNECTION_CONFIRMED, stop.
    succeeds                     -> proceed to Layer D.

  Layer D (real historical fetch -> real TechnicalAnalysisEngine ->
           real RecommendationEngine, symbol 2222)
    historical endpoint 403s     -> SAHMK_PLAN_RESTRICTION, stop.
        (explicitly an entitlement limitation per the task spec, not
        a program failure -- Layer B/C already proved the connection,
        key, and client/parser all work correctly)
    network error mid-layer      -> SAHMK_NETWORK_BLOCKED, stop.
    historical parsing raises    -> BASIRAH_PARSER_MISMATCH, stop.
    TechnicalAnalysisEngine or
    RecommendationEngine raises  -> BASIRAH_PIPELINE_BROKEN, stop.
    not run (defensive only)     -> SAHMK_CONNECTION_CONFIRMED, stop.
    succeeds                     -> FULL_END_TO_END_SUCCESS.

INCONCLUSIVE is a disclosed extension beyond the 8 diagnoses the task
enumerates. A 429/5xx on the one mandatory call, or a 200 whose body
SAHMK itself (not Basirah) made unusable, is a real, distinct outcome
that does not truthfully match SAHMK_NETWORK_BLOCKED (SAHMK was
reached and answered), SAHMK_KEY_INVALID, or SAHMK_PLAN_RESTRICTION.
Silently forcing it into one of those would misreport what actually
happened. It is reported honestly instead, and the workflow exits
non-zero so it is never mistaken for a clean pass.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Diagnosis(str, Enum):
    """The 8 required final diagnoses, plus the disclosed INCONCLUSIVE
    extension described in this module's docstring."""

    SAHMK_CONNECTION_CONFIRMED = "SAHMK_CONNECTION_CONFIRMED"
    SAHMK_KEY_INVALID = "SAHMK_KEY_INVALID"
    SAHMK_PLAN_RESTRICTION = "SAHMK_PLAN_RESTRICTION"
    SAHMK_NETWORK_BLOCKED = "SAHMK_NETWORK_BLOCKED"
    BASIRAH_CLIENT_BROKEN = "BASIRAH_CLIENT_BROKEN"
    BASIRAH_PARSER_MISMATCH = "BASIRAH_PARSER_MISMATCH"
    BASIRAH_PIPELINE_BROKEN = "BASIRAH_PIPELINE_BROKEN"
    FULL_END_TO_END_SUCCESS = "FULL_END_TO_END_SUCCESS"
    INCONCLUSIVE = "INCONCLUSIVE"


# Diagnoses that mean the diagnostic run itself completed and reached a
# real, decisive answer -- including "bad" answers like SAHMK_KEY_INVALID,
# which is a conclusive fact about the key, not a broken script. Only
# INCONCLUSIVE (an outcome the 8-value spec has no slot for) should ever
# fail the job mechanically.
CONCLUSIVE_DIAGNOSES = frozenset(d for d in Diagnosis if d is not Diagnosis.INCONCLUSIVE)


class LayerAResult(str, Enum):
    OK = "ok"
    NETWORK_BLOCKED = "network_blocked"


class LayerBOutcome(str, Enum):
    """Raw classification of the mandatory GET /quote/2222/ call."""

    OK = "ok"
    KEY_INVALID = "key_invalid"
    PLAN_RESTRICTED = "plan_restricted"
    NETWORK_BLOCKED = "network_blocked"
    RATE_LIMITED = "rate_limited"
    SERVER_ERROR = "server_error"
    CONTRACT_MISMATCH = "contract_mismatch"


def classify_layer_b(
    *,
    status_code: Optional[int],
    network_error: bool,
    is_json: bool,
    has_required_fields: bool,
) -> LayerBOutcome:
    """`status_code` is None iff `network_error` is True (the request
    never got an HTTP response at all). `has_required_fields` is only
    meaningful when `status_code == 200` and `is_json` is True -- it
    means the response contains at least a usable `price` value (see
    verify_sahmk_live.py's field-extraction step)."""
    if network_error or status_code is None:
        return LayerBOutcome.NETWORK_BLOCKED
    if status_code == 200:
        if not is_json or not has_required_fields:
            return LayerBOutcome.CONTRACT_MISMATCH
        return LayerBOutcome.OK
    if status_code == 401:
        return LayerBOutcome.KEY_INVALID
    if status_code == 403:
        return LayerBOutcome.PLAN_RESTRICTED
    if status_code == 429:
        return LayerBOutcome.RATE_LIMITED
    if 500 <= status_code < 600:
        return LayerBOutcome.SERVER_ERROR
    # Any other status this integration has no documented mapping for
    # (docs/SAHMK_INTEGRATION.md's "Error handling" section) -- treated
    # the same as a malformed response rather than guessed at.
    return LayerBOutcome.CONTRACT_MISMATCH


class LayerCOutcome(str, Enum):
    NOT_RUN = "not_run"
    CLIENT_ERROR = "client_error"
    PARSER_ERROR = "parser_error"
    OK = "ok"


class LayerDOutcome(str, Enum):
    NOT_RUN = "not_run"
    PLAN_RESTRICTED = "plan_restricted"
    NETWORK_BLOCKED = "network_blocked"
    PARSER_ERROR = "parser_error"
    PIPELINE_ERROR = "pipeline_error"
    OK = "ok"


@dataclass(frozen=True)
class LayerOutcomes:
    layer_a: LayerAResult
    layer_b: LayerBOutcome
    layer_c: LayerCOutcome = LayerCOutcome.NOT_RUN
    layer_d: LayerDOutcome = LayerDOutcome.NOT_RUN


def determine_final_diagnosis(outcomes: LayerOutcomes) -> Diagnosis:
    """The single decision tree described in this module's docstring.
    Each `if` corresponds exactly to one line of that tree, in the same
    order, so the two never drift apart silently."""

    if outcomes.layer_a == LayerAResult.NETWORK_BLOCKED:
        return Diagnosis.SAHMK_NETWORK_BLOCKED

    if outcomes.layer_b == LayerBOutcome.NETWORK_BLOCKED:
        return Diagnosis.SAHMK_NETWORK_BLOCKED
    if outcomes.layer_b == LayerBOutcome.KEY_INVALID:
        return Diagnosis.SAHMK_KEY_INVALID
    if outcomes.layer_b == LayerBOutcome.PLAN_RESTRICTED:
        return Diagnosis.SAHMK_PLAN_RESTRICTION
    if outcomes.layer_b in (
        LayerBOutcome.RATE_LIMITED,
        LayerBOutcome.SERVER_ERROR,
        LayerBOutcome.CONTRACT_MISMATCH,
    ):
        return Diagnosis.INCONCLUSIVE

    # outcomes.layer_b == OK from here on.
    if outcomes.layer_c == LayerCOutcome.CLIENT_ERROR:
        return Diagnosis.BASIRAH_CLIENT_BROKEN
    if outcomes.layer_c == LayerCOutcome.PARSER_ERROR:
        return Diagnosis.BASIRAH_PARSER_MISMATCH
    if outcomes.layer_c == LayerCOutcome.NOT_RUN:
        return Diagnosis.SAHMK_CONNECTION_CONFIRMED

    # outcomes.layer_c == OK from here on.
    if outcomes.layer_d == LayerDOutcome.PLAN_RESTRICTED:
        return Diagnosis.SAHMK_PLAN_RESTRICTION
    if outcomes.layer_d == LayerDOutcome.NETWORK_BLOCKED:
        return Diagnosis.SAHMK_NETWORK_BLOCKED
    if outcomes.layer_d == LayerDOutcome.PARSER_ERROR:
        return Diagnosis.BASIRAH_PARSER_MISMATCH
    if outcomes.layer_d == LayerDOutcome.PIPELINE_ERROR:
        return Diagnosis.BASIRAH_PIPELINE_BROKEN
    if outcomes.layer_d == LayerDOutcome.NOT_RUN:
        return Diagnosis.SAHMK_CONNECTION_CONFIRMED

    return Diagnosis.FULL_END_TO_END_SUCCESS


DIAGNOSIS_MEANINGS = {
    Diagnosis.SAHMK_CONNECTION_CONFIRMED: (
        "Network, DNS, TLS, API key, and the basic quote endpoint all work."
    ),
    Diagnosis.SAHMK_KEY_INVALID: "The API returned 401 -- the configured SAHMK_API_KEY was rejected.",
    Diagnosis.SAHMK_PLAN_RESTRICTION: (
        "Authentication succeeded but one or more required endpoints returned 403 "
        "(plan/entitlement limit)."
    ),
    Diagnosis.SAHMK_NETWORK_BLOCKED: "DNS, TLS, connection, or timeout prevented reaching SAHMK.",
    Diagnosis.BASIRAH_CLIENT_BROKEN: (
        "The direct official API request succeeded but Basirah's own SahmkClient failed."
    ),
    Diagnosis.BASIRAH_PARSER_MISMATCH: (
        "The direct API request succeeded but Basirah could not parse the real response."
    ),
    Diagnosis.BASIRAH_PIPELINE_BROKEN: (
        "The client and parser succeeded but the real data could not complete the "
        "analysis/recommendation pipeline."
    ),
    Diagnosis.FULL_END_TO_END_SUCCESS: (
        "Real Saudi market data was fetched from SAHMK and successfully passed through "
        "Basirah to a real analysis/recommendation result."
    ),
    Diagnosis.INCONCLUSIVE: (
        "The mandatory quote call reached SAHMK and got a definite answer that does not "
        "match any of the 8 defined diagnoses (e.g. a 429, a 5xx, or a malformed 200 body). "
        "Not a clean pass -- re-run once the underlying condition clears."
    ),
}
