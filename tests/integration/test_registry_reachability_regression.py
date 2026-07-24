"""Dedicated regression guard for the dormant DEFAULT_EXPERT_REGISTRY
defect found and fixed at M2.10 (see the detailed root-cause writeup
in tests/integration/test_full_pipeline.py's own module docstring).

This file exists for exactly one reason: to fail, immediately and with
an unambiguous message, if the specific fix in test_full_pipeline.py
(its `import src.analysis.experts.bootstrap` line) is ever accidentally
removed again -- without requiring anyone to remember to re-run that
file in true isolation to notice.

Why a subprocess, not just "run this file alone via pytest": running a
test file alone via `pytest some_file.py` still shares the same Python
process, and therefore the same already-imported-module cache
(`sys.modules`), as pytest's own collection machinery and any plugin it
loads. In this repository specifically that risk is low (there is no
conftest.py anywhere, confirmed directly, so no shared fixture could
mask this defect the way it was masked before), but a subprocess check
is immune to that risk by construction, not by inspection of the
current absence of a conftest.py -- it starts a genuinely fresh
Python interpreter with an empty sys.modules, importing only what the
subprocess script itself imports. This is the same guarantee
tests/unit/test_main_boot.py's `import main` achieves for main.py's
own reachability (a real process boot), applied here to
test_full_pipeline.py's narrower, file-specific dependency.
"""

import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]

_SUBPROCESS_SCRIPT = (
    "import tests.integration.test_full_pipeline\n"
    "from src.analysis.experts.registry import DEFAULT_EXPERT_REGISTRY\n"
    "from src.analysis.core.registry import DEFAULT_ENGINE_REGISTRY\n"
    "expert_ids = sorted(spec.expert_id for spec in DEFAULT_EXPERT_REGISTRY.all_specs())\n"
    "engine_names = sorted(spec.name for spec in DEFAULT_ENGINE_REGISTRY.all_specs())\n"
    "assert len(expert_ids) >= 4, (\n"
    "    'DEFAULT_EXPERT_REGISTRY has only ' + str(len(expert_ids)) + ' registered expert(s) '\n"
    "    + repr(expert_ids) + ' after importing tests.integration.test_full_pipeline alone '\n"
    "    'in a fresh interpreter -- the dormant-registry defect fixed at M2.10 has '\n"
    "    'regressed (see that test file own module docstring for the full root-cause '\n"
    "    'writeup). Check that it still imports src.analysis.experts.bootstrap.'\n"
    ")\n"
    "assert 'technical_council' in engine_names, (\n"
    "    'DEFAULT_ENGINE_REGISTRY is missing technical_council '\n"
    "    '(has: ' + repr(engine_names) + ') after importing '\n"
    "    'tests.integration.test_full_pipeline alone in a fresh interpreter -- '\n"
    "    'same regression as above, one registry over.'\n"
    ")\n"
    "print('REGISTRY_REACHABILITY_OK')\n"
)


def test_importing_full_pipeline_test_module_alone_populates_both_registries():
    """Regression guard: importing tests.integration.test_full_pipeline,
    and nothing else, in a brand-new Python process, must be sufficient
    on its own to populate DEFAULT_EXPERT_REGISTRY (>=4 experts) and
    DEFAULT_ENGINE_REGISTRY's "technical_council" entry -- exactly the
    guarantee test_full_pipeline.py's Stage 7 silently relied on without
    actually holding, before the M2.10 fix.
    """
    result = subprocess.run(
        [sys.executable, "-c", _SUBPROCESS_SCRIPT],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, (
        f"Fresh-interpreter reachability check failed.\n"
        f"--- stdout ---\n{result.stdout}\n"
        f"--- stderr ---\n{result.stderr}"
    )
    assert "REGISTRY_REACHABILITY_OK" in result.stdout


def test_no_conftest_silently_supplies_the_registration_side_effect():
    """Guards the assumption the module docstring above states as fact,
    not merely as reassurance: if a future conftest.py is ever added
    anywhere in the repository and happens to import
    src.analysis.experts.bootstrap (or .technical) as a side effect,
    that conftest.py -- not this file's own explicit import -- would
    become the thing silently making test_full_pipeline.py's Stage 7
    pass, exactly the failure mode this whole regression suite exists
    to prevent. This test does not forbid a future conftest.py; it
    only requires whoever adds one to consciously revisit this file's
    docstring and this guard, since the docstring's reasoning would no
    longer hold as stated.
    """
    conftest_files = list(_REPO_ROOT.rglob("conftest.py"))
    assert conftest_files == [], (
        f"A conftest.py now exists ({[str(p) for p in conftest_files]}) where none did "
        f"when this regression test was written (M2.10). Re-verify "
        f"tests/integration/test_full_pipeline.py's own registry-reachability "
        f"import is still doing the real work, not being masked by the new "
        f"conftest.py's own import side effects, then update this test's "
        f"docstring and assertion accordingly -- do not simply delete this guard."
    )
