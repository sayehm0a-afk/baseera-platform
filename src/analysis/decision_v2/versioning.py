"""QUALITY PROOF INSTRUMENTATION HARDENING (2026-09-06): per-signal,
immutable experiment-version provenance for `DecisionV2Snapshot`.

This module computes zero recommendation logic -- it only reads
already-existing, already-frozen configuration values and identifies
the running code version, so a forward-test cohort can later prove
"every signal in this window came from the exact same engine
behavior." Nothing here is read by `DecisionEngineV2.decide()`,
`evaluate_decision()`, or any other decision-facing function; callers
compute these values once and attach them to the snapshot at INSERT
time only (see `src.api.routes.stocks` and
`src.market_intelligence.repositories.market_intelligence_repository`).
Once persisted, `DecisionV2Snapshot.engine_sha`/`.config_hash` are
never recomputed for that row -- see `LEGACY_UNVERSIONED` below for
rows written before this module existed.

`ENGINE_SHA`: the exact deployed commit (`DEPLOYMENT_COMMIT`, the same
env var `GET /admin/system/summary` already reports as
`deployment_commit` -- reused, not reinvented). Falls back to a
git-derived local value outside a deployed environment (e.g. running
tests locally), never to an opaque timestamp -- a timestamp cannot be
diffed against another run's code, a commit SHA can.

`CONFIG_HASH`: a stable SHA-256 fingerprint of every runtime-adjustable
value capable of changing Decision V2's output for the same market
input -- `DecisionV2Tuning`'s full field set (currently hardcoded, but
this must still be captured in case a future change makes any of it
env-configurable) plus the four env-var-driven gate thresholds
`gates.py`/`engine.py` read directly from
`src.market_intelligence.config` (max data age, max OHLCV staleness,
min risk/reward, min average traded value) -- exactly the
"behavior-changing configuration" the mandate's cohort-isolation rule
needs, and precisely what `ENGINE_SHA` alone cannot capture (an
operator can change an env var without any new commit). Deliberately
excludes anything that cannot affect Decision V2's own decide() output
(e.g. ingestion cadence, SAHMK quota partitions, Radar candidate caps)
-- those are separate concerns with their own provenance elsewhere.
"""

import hashlib
import json
import subprocess
from dataclasses import asdict
from typing import Optional

LEGACY_UNVERSIONED = "LEGACY_UNVERSIONED"


def _git_head_sha_fallback() -> Optional[str]:
    """Best-effort local git SHA for a non-deployed environment (local
    dev, unit tests) -- never used in a real Railway deployment, where
    `DEPLOYMENT_COMMIT` is always set (see deploy-railway.yml). Returns
    None (never a fabricated value) if git is unavailable."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def get_engine_sha() -> str:
    """The exact code version responsible for a Decision V2 signal --
    the deployed commit SHA, never a runtime timestamp. Falls back to
    a local git HEAD read (dev/test), and only as a last resort to a
    fixed sentinel ('UNKNOWN_ENGINE_SHA') so this can never raise and
    block a real decision from being persisted."""
    from src.core.config.settings import settings

    if settings.deployment_commit:
        return settings.deployment_commit
    local_sha = _git_head_sha_fallback()
    return local_sha or "UNKNOWN_ENGINE_SHA"


def _decision_v2_tuning_fingerprint_dict() -> dict:
    from src.analysis.decision_v2.config import DecisionV2Tuning
    from src.market_intelligence.config import (
        get_max_data_age_hours,
        get_max_ohlcv_staleness_days,
        get_min_average_traded_value,
        get_min_risk_reward_ratio,
    )

    payload = asdict(DecisionV2Tuning())
    payload["max_data_age_hours"] = get_max_data_age_hours()
    payload["max_ohlcv_staleness_days"] = get_max_ohlcv_staleness_days()
    payload["min_risk_reward_ratio"] = get_min_risk_reward_ratio()
    payload["min_average_traded_value"] = get_min_average_traded_value()
    return payload


def compute_decision_v2_config_hash() -> str:
    """Deterministic: identical configuration always yields the
    identical hash (canonical JSON, sorted keys, no whitespace
    ambiguity); any behavior-changing value above yields a different
    one. Deliberately uncached -- the four env-var getters this reads
    are themselves uncached (`os.getenv()` on every call, matching
    this codebase's existing convention), and a genuinely cheap
    dataclass-plus-four-lookups computation gains nothing from caching
    while risking a stale hash surviving a same-process config change
    (e.g. in a test that monkeypatches an env var)."""
    payload = _decision_v2_tuning_fingerprint_dict()
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
