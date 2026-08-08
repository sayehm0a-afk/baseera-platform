"""Prints bar count + first/last bar from a saved /stocks/{symbol}/history
response. Used by production-ohlcv-gap-probe.yml to avoid embedding
multi-line Python inside a YAML run block (which is fragile to indent)."""

import json
import sys

path = sys.argv[1]
try:
    with open(path) as f:
        data = json.load(f)
    bars = data.get("bars") or []
    print("bar_count:", len(bars))
    if bars:
        print("first_bar:", bars[0])
        print("last_bar:", bars[-1])
except Exception as exc:
    print("could not parse history response:", exc)
    with open(path) as f:
        print(f.read()[:500])
