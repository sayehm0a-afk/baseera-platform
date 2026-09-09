"""Verify source-level isolation from a pinned review baseline (no imports)."""

import hashlib
import json
import subprocess
from pathlib import Path

BASE = "88374a438829b90f34d8da58a37ccdc9f6c6a2a3"
PREFIXES = ("src/analysis/", "src/ai/", "src/market_intelligence/", "src/market_data/", "src/ai_evolution/")


def build_manifest(root: Path):
    paths = subprocess.check_output(["git", "ls-tree", "-r", "--name-only", BASE, "src"], cwd=root, text=True).splitlines()
    records = []
    for path in paths:
        if not path.startswith(PREFIXES):
            continue
        original = subprocess.check_output(["git", "show", f"{BASE}:{path}"], cwd=root)
        current = (root / path).read_bytes() if (root / path).exists() else b""
        records.append({"path": path, "baseline_sha256": hashlib.sha256(original).hexdigest(),
                        "current_sha256": hashlib.sha256(current).hexdigest(), "unchanged": original == current})
    # Also detect newly added protected files, which the baseline tree cannot list.
    known = {r["path"] for r in records}
    added = [str(p.relative_to(root)) for prefix in PREFIXES for p in (root / prefix).rglob("*.py")
             if str(p.relative_to(root)) not in known]
    return {"baseline": BASE, "all_unchanged": all(r["unchanged"] for r in records) and not added,
            "new_protected_files": sorted(added), "files": records,
            "limitation": "Source identity only; dependency versions and fixed-input tests must be checked separately."}


if __name__ == "__main__":
    manifest = build_manifest(Path(__file__).resolve().parents[2])
    print(json.dumps(manifest, indent=2))
    raise SystemExit(0 if manifest["all_unchanged"] else 1)
