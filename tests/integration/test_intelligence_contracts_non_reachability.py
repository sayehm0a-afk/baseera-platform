"""Regression guard for the explicit constraint this package was built
under: "prepare the architecture... without implementing any of them...
and without changing any production behavior."

Mirrors tests/integration/test_ail_contracts_non_reachability.py's
subprocess technique exactly, applied to
src.analysis.intelligence.contracts instead of
src.core.autonomous_intelligence_layer.contracts: proves the package is
NOT reachable from `import main`, and that main's existing registries
(DEFAULT_ENGINE_REGISTRY, DEFAULT_EXPERT_REGISTRY) are byte-identical
in membership to what they were before this package existed.

A subprocess, not an in-process check, for the same immunity to
sys.modules pollution from pytest's own collection.
"""

import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]

_SUBPROCESS_SCRIPT = (
    "import sys\n"
    "import main\n"
    "intelligence_contracts_modules = sorted(\n"
    "    name for name in sys.modules\n"
    "    if name.startswith('src.analysis.intelligence.contracts')\n"
    ")\n"
    "assert intelligence_contracts_modules == [], (\n"
    "    'Importing main.py pulled in Decision & Intelligence Modules contracts '\n"
    "    + repr(intelligence_contracts_modules) + ' -- this package must stay '\n"
    "    'unreachable from the production entry point until a future, '\n"
    "    'separately-approved milestone deliberately wires it in. See '\n"
    "    'src/analysis/intelligence/contracts/integration.py for why there is no '\n"
    "    'bootstrap.py for it yet.'\n"
    ")\n"
    "from src.analysis.core.registry import DEFAULT_ENGINE_REGISTRY\n"
    "from src.analysis.experts.registry import DEFAULT_EXPERT_REGISTRY\n"
    "engine_names = sorted(spec.name for spec in DEFAULT_ENGINE_REGISTRY.all_specs())\n"
    "expert_ids = sorted(spec.expert_id for spec in DEFAULT_EXPERT_REGISTRY.all_specs())\n"
    "expected_engine_names = [\n"
    "    'composite_analysis', 'fundamental_analysis', 'technical_analysis', 'technical_council'\n"
    "]\n"
    "expected_expert_ids = [\n"
    "    'technical.candlestick', 'technical.momentum', 'technical.trend', "
    "'technical.volatility', 'technical.volume'\n"
    "]\n"
    "assert engine_names == expected_engine_names, (\n"
    "    'DEFAULT_ENGINE_REGISTRY changed after adding the intelligence contracts '\n"
    "    'package: expected ' + repr(expected_engine_names) + ', got ' + repr(engine_names) + '. '\n"
    "    'This package must not change any existing production registry.'\n"
    ")\n"
    "assert expert_ids == expected_expert_ids, (\n"
    "    'DEFAULT_EXPERT_REGISTRY changed after adding the intelligence contracts '\n"
    "    'package: expected ' + repr(expected_expert_ids) + ', got ' + repr(expert_ids) + '. '\n"
    "    'This package must not change any existing production registry.'\n"
    ")\n"
    "from src.analysis.intelligence.contracts.registry import (\n"
    "    DEFAULT_INTELLIGENCE_MODULE_REGISTRY,\n"
    ")\n"
    "assert DEFAULT_INTELLIGENCE_MODULE_REGISTRY.all_specs() == [], (\n"
    "    'DEFAULT_INTELLIGENCE_MODULE_REGISTRY is no longer empty -- this is the '\n"
    "    'extension point itself, not populated content; nothing should register '\n"
    "    'into it without a separately-approved milestone deciding to.'\n"
    ")\n"
    "print('INTELLIGENCE_CONTRACTS_NON_REACHABILITY_OK')\n"
)


def test_importing_main_does_not_import_intelligence_contracts_or_change_existing_registries():
    result = subprocess.run(
        [sys.executable, "-c", _SUBPROCESS_SCRIPT],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, (
        f"Fresh-interpreter non-reachability check failed.\n"
        f"--- stdout ---\n{result.stdout}\n"
        f"--- stderr ---\n{result.stderr}"
    )
    assert "INTELLIGENCE_CONTRACTS_NON_REACHABILITY_OK" in result.stdout


def test_intelligence_contracts_package_has_no_bootstrap_module():
    # A bootstrap.py appearing here would be the first line of code
    # wiring this package into main.py's import chain -- its absence is
    # the second half of the non-reachability guarantee.
    bootstrap_path = (
        _REPO_ROOT / "src" / "analysis" / "intelligence" / "contracts" / "bootstrap.py"
    )
    assert not bootstrap_path.exists(), (
        "src/analysis/intelligence/contracts/bootstrap.py now exists. Creating it "
        "is the deliberate act of wiring this package into production and must not "
        "happen silently -- see integration.py point 4. If a future, "
        "separately-approved milestone has genuinely decided to wire this package "
        "in, update this test (and this package's docstrings) deliberately rather "
        "than deleting the guard."
    )
