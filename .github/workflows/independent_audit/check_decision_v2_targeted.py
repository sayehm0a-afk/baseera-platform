"""One-off, temporary, read-only diagnostic (NOT merged to main): calls
the existing, unmodified production GET /api/v1/stocks/{symbol}/decision-v2
route for a fixed, caller-approved list of symbols only.

Purpose: obtain a genuinely fresh Decision V2 evaluation for a handful of
specific symbols during a live market session, without running Stage 1 or
a market-wide scan. This route already exists in production
(src/api/routes/stocks.py) and is exercised by real users/the frontend on
every stock-detail page view -- this script does nothing the app doesn't
already do, it just calls it directly for named symbols.

Each call to this route makes exactly one live SAHMK provider request
(src/analysis/context_builder.py's _build_analysis_context() calls
market_provider.get_stock_data(symbol) once, nothing else) -- so N
symbols costs N SAHMK requests, never more.

No Stage 1, no market-wide scan, no other endpoint calls, no writes
beyond what the route itself already does (a best-effort DecisionV2Snapshot
audit row, exactly as it does for any real user viewing a stock page).
"""

import json
import os
import sys

import requests

BACKEND_URL = os.environ["BACKEND_URL"].rstrip("/")
STAFF_EMAIL = os.environ["STAFF_EMAIL"]
STAFF_PASSWORD = os.environ["STAFF_PASSWORD"]
SYMBOLS = [s.strip() for s in os.environ["SYMBOLS_INPUT"].split(",") if s.strip()]

session = requests.Session()
r = session.post(
    f"{BACKEND_URL}/api/v1/auth/login",
    json={"email": STAFF_EMAIL, "password": STAFF_PASSWORD},
    timeout=30,
)
if r.status_code != 200:
    print(f"Staff login failed: status={r.status_code} body={r.text[:500]}")
    sys.exit(1)

results = {}
for symbol in SYMBOLS:
    r = session.get(f"{BACKEND_URL}/api/v1/stocks/{symbol}/decision-v2", timeout=60)
    if r.status_code != 200:
        results[symbol] = {"ERROR": f"status={r.status_code} body={r.text[:500]}"}
        continue
    results[symbol] = r.json()

print("===DECISION_V2_TARGETED_JSON_START===")
print(json.dumps(results, indent=2, default=str))
print("===DECISION_V2_TARGETED_JSON_END===")
