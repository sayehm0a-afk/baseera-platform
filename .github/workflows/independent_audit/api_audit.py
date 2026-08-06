"""Independent, assumption-free production API audit.

Exercises real production endpoints as an external user would: an
anonymous visitor, a brand-new self-registered customer going through
the actual email-verification wall, and the staff account. No mocking,
no shortcuts through the app layer -- every call is a real HTTP
request against BACKEND_URL. Prints a structured PASS/FAIL/INFO log
and a final summary; exits non-zero only if a genuine defect (not an
expected-and-correct rejection) was found, so the calling workflow's
job status reflects real audit outcome.

This script and the workflow that runs it are throwaway audit tooling,
not application code -- deleted once the audit's evidence is captured,
same convention as the earlier final-production-audit.yml pass.
"""

import json
import os
import re
import subprocess
import sys
import time
import uuid

import requests

BACKEND_URL = os.environ["BACKEND_URL"].rstrip("/")
STAFF_EMAIL = os.environ["STAFF_EMAIL"]
STAFF_PASSWORD = os.environ["STAFF_PASSWORD"]
RAILWAY_BACKEND_SERVICE = os.environ.get("RAILWAY_BACKEND_SERVICE", "backend")

results = []


def railway_logs(tail=3000):
    try:
        proc = subprocess.run(
            ["timeout", "25", "railway", "logs", "--service", RAILWAY_BACKEND_SERVICE],
            capture_output=True, text=True, timeout=30,
        )
        lines = (proc.stdout + proc.stderr).splitlines()
        return "\n".join(lines[-tail:])
    except Exception as exc:  # noqa: BLE001 -- log retrieval failure is evidence, not a crash
        return f"__RAILWAY_LOGS_UNAVAILABLE__: {exc}"


def check_smtp_configured():
    try:
        proc = subprocess.run(
            ["railway", "variable", "list", "--service", RAILWAY_BACKEND_SERVICE, "--json"],
            capture_output=True, text=True, timeout=30,
        )
        data = json.loads(proc.stdout or "{}")
        val = data.get("SMTP_HOST")
        return bool(val and val.strip())
    except Exception as exc:  # noqa: BLE001
        return f"__CHECK_FAILED__: {exc}"


def record(check, status, detail=""):
    results.append({"check": check, "status": status, "detail": detail})
    marker = {"PASS": "OK", "FAIL": "**FAIL**", "INFO": "info", "WARN": "WARN"}[status]
    print(f"[{marker}] {check}" + (f" -- {detail}" if detail else ""))


def call(session, method, path, csrf=None, **kw):
    headers = kw.pop("headers", {})
    if csrf:
        headers["X-CSRF-Token"] = csrf
    url = f"{BACKEND_URL}{path}"
    try:
        resp = session.request(method, url, headers=headers, timeout=30, **kw)
        return resp
    except requests.RequestException as exc:
        return exc


def get_csrf(session):
    return session.cookies.get("csrf_token")


# ---------------------------------------------------------------------------
# 0. Anonymous / unauthenticated surface
# ---------------------------------------------------------------------------
print("\n=== 0. Anonymous surface ===")
anon = requests.Session()

for path, expect in [("/health/live", 200), ("/health/ready", 200), ("/health/market-data", 200)]:
    r = call(anon, "GET", path)
    ok = isinstance(r, requests.Response) and r.status_code == expect
    record(f"GET {path} (anonymous)", "PASS" if ok else "FAIL",
           f"expected {expect}, got {getattr(r, 'status_code', r)}")

# Docs must NOT be publicly reachable in production.
r = call(anon, "GET", "/docs")
docs_exposed = isinstance(r, requests.Response) and r.status_code == 200
record("GET /docs is disabled in production", "PASS" if not docs_exposed else "FAIL",
       f"status={getattr(r, 'status_code', r)}")

# Protected endpoints must reject anonymous callers, not 500.
for path in ["/api/v1/auth/me", "/api/v1/stocks/2222/quote", "/api/v1/admin/system/summary",
             "/api/v1/portfolio/1"]:
    r = call(anon, "GET", path)
    code = getattr(r, "status_code", None)
    ok = code in (401, 403)
    record(f"GET {path} (anonymous) rejected, not 500", "PASS" if ok else "FAIL", f"status={code}")

# ---------------------------------------------------------------------------
# 1. Real external-user registration journey
# ---------------------------------------------------------------------------
print("\n=== 1. New customer registration journey ===")
unique = uuid.uuid4().hex[:12]
test_email = f"basirah-audit-{unique}@example.com"
test_password = "AuditP@ssw0rd123"

reg = requests.Session()
r = call(reg, "POST", "/api/v1/auth/register", json={"email": test_email, "password": test_password, "full_name": "Audit Bot"})
code = getattr(r, "status_code", None)
record("POST /auth/register (new unique email)", "PASS" if code in (200, 201) else "FAIL", f"status={code}")
if isinstance(r, requests.Response) and r.status_code in (200, 201):
    body = r.json()
    leaked_token = any(k for k in json.dumps(body).lower().split() if "token" in k)
    record("Register response does not leak a raw token in the body", "PASS" if not leaked_token else "FAIL",
           json.dumps(body)[:300])

# Duplicate registration must be a clean error, not a 500.
r = call(reg, "POST", "/api/v1/auth/register", json={"email": test_email, "password": test_password})
code = getattr(r, "status_code", None)
record("POST /auth/register duplicate email rejected cleanly", "PASS" if code in (400, 409, 422) else "FAIL",
       f"status={code}")

# Weak password must be a validation error, not accepted, not a 500.
r = call(anon, "POST", "/api/v1/auth/register",
         json={"email": f"weakpw-{unique}@example.com", "password": "short"})
code = getattr(r, "status_code", None)
record("POST /auth/register short password rejected (422)", "PASS" if code == 422 else "FAIL", f"status={code}")

# Login before verifying email -- this SHOULD be blocked (correct security
# behavior). Recorded as INFO, not a failure, unless it's not blocked.
login_new = requests.Session()
r = call(login_new, "POST", "/api/v1/auth/login", json={"email": test_email, "password": test_password})
code = getattr(r, "status_code", None)
if code == 200:
    record("Login before email verification", "FAIL", "SECURITY: unverified account was allowed to log in")
else:
    record("Login before email verification correctly blocked", "PASS" if code in (401, 403) else "FAIL",
           f"status={code}")

# Wrong password / nonexistent email must not be 500 and should not
# obviously distinguish "account exists" from "account doesn't exist".
r1 = call(anon, "POST", "/api/v1/auth/login", json={"email": STAFF_EMAIL, "password": "definitely-wrong-password"})
r2 = call(anon, "POST", "/api/v1/auth/login", json={"email": f"nobody-{unique}@example.com", "password": "whatever123"})
c1, c2 = getattr(r1, "status_code", None), getattr(r2, "status_code", None)
record("POST /auth/login wrong password (real account) -> 401, not 500", "PASS" if c1 == 401 else "FAIL", f"status={c1}")
record("POST /auth/login nonexistent email -> 401, not 500", "PASS" if c2 == 401 else "FAIL", f"status={c2}")
if isinstance(r1, requests.Response) and isinstance(r2, requests.Response):
    same_shape = r1.status_code == r2.status_code and set(r1.json().keys()) == set(r2.json().keys())
    record("Login error responses don't obviously leak account existence", "PASS" if same_shape else "WARN",
           f"wrong-password body={r1.text[:150]} | nonexistent body={r2.text[:150]}")

# ---------------------------------------------------------------------------
# 2. Does a real external user have ANY way to complete verification today?
# ---------------------------------------------------------------------------
print("\n=== 2. Email delivery reality check ===")
smtp_configured = check_smtp_configured()
record("SMTP_HOST configured on backend (production email delivery)", "INFO", str(smtp_configured))

verify_token = ""
if smtp_configured is False:
    # No real mail provider is configured -- the ONLY place the
    # verification token exists is the backend's own log stream
    # (ConsoleEmailSender, by design, logs it instead of sending it).
    # Recover it the same way an operator manually rescuing a stuck
    # signup would have to -- this both completes the audit's journey
    # and is itself the evidence for whether that manual rescue is
    # even necessary.
    time.sleep(3)
    logs = railway_logs()
    pattern = re.compile(
        r"verification email NOT actually sent to " + re.escape(test_email) + r"\. Token: (\S+)"
    )
    match = pattern.search(logs)
    if match:
        verify_token = match.group(1)
        record("Verification token recoverable from backend logs (ConsoleEmailSender)", "INFO",
               "token found in logs -- confirms no real email was sent to the user")
    else:
        record("Verification token search in backend logs", "WARN",
               "SMTP not configured, but no matching ConsoleEmailSender log line found either")
elif smtp_configured is True:
    record("Real SMTP provider is configured", "INFO",
           "verification email should have been sent to a real inbox this audit cannot access")
else:
    record("Could not determine SMTP_HOST configuration", "WARN", str(smtp_configured))

verified_ok = False
if verify_token:
    r = call(login_new, "POST", "/api/v1/auth/verify-email", json={"token": verify_token})
    code = getattr(r, "status_code", None)
    verified_ok = code == 200
    record("POST /auth/verify-email with token recovered from backend logs", "PASS" if verified_ok else "FAIL",
           f"status={code}")
    if verified_ok:
        r = call(login_new, "POST", "/api/v1/auth/login", json={"email": test_email, "password": test_password})
        code = getattr(r, "status_code", None)
        record("Login after verification succeeds", "PASS" if code == 200 else "FAIL", f"status={code}")
        verified_ok = code == 200
else:
    record("No verification token was recoverable for this audit run",
           "INFO", "see SMTP_HOST_CONFIGURED above for why")

if verified_ok:
    print("\n=== 2b. RBAC boundary check (real non-staff authenticated session) ===")
    new_csrf = get_csrf(login_new)
    for path in ["/api/v1/admin/system/summary", "/api/v1/admin/users", "/api/v1/admin/sessions"]:
        r = call(login_new, "GET", path)
        code = getattr(r, "status_code", None)
        record(f"GET {path} (real non-staff user) rejected, not 500", "PASS" if code == 403 else "FAIL",
               f"status={code}")
    # A brand-new trial user should still reach ordinary customer features.
    r = call(login_new, "GET", "/api/v1/stocks/2222/quote")
    code = getattr(r, "status_code", None)
    record("GET /stocks/2222/quote (real trial user)", "PASS" if code == 200 else "FAIL", f"status={code}")
else:
    record("RBAC boundary check as a real non-staff user", "WARN",
           "skipped -- no verified non-staff session available this run (see email delivery check above)")

# ---------------------------------------------------------------------------
# 3. Staff session -- the reliable, always-available authenticated identity
# ---------------------------------------------------------------------------
print("\n=== 3. Staff session ===")
staff = requests.Session()
r = call(staff, "POST", "/api/v1/auth/login", json={"email": STAFF_EMAIL, "password": STAFF_PASSWORD})
code = getattr(r, "status_code", None)
record("POST /auth/login (staff account)", "PASS" if code == 200 else "FAIL", f"status={code}")
if code != 200:
    print("Cannot continue authenticated checks without a staff session.")
    print(json.dumps(results, indent=2))
    sys.exit(1)
staff_csrf = get_csrf(staff)

r = call(staff, "GET", "/api/v1/auth/me")
code = getattr(r, "status_code", None)
is_staff_flag = isinstance(r, requests.Response) and r.status_code == 200 and r.json().get("is_staff")
record("GET /auth/me (staff) shows is_staff=true", "PASS" if is_staff_flag else "FAIL", f"status={code}")

r = call(staff, "GET", "/api/v1/subscriptions/me")
record("GET /subscriptions/me (staff)", "PASS" if getattr(r, "status_code", None) == 200 else "FAIL",
       f"status={getattr(r, 'status_code', None)}")

r = call(staff, "GET", "/api/v1/auth/sessions")
record("GET /auth/sessions (staff)", "PASS" if getattr(r, "status_code", None) == 200 else "FAIL",
       f"status={getattr(r, 'status_code', None)}")

r = call(staff, "GET", "/api/v1/auth/me/export")
code = getattr(r, "status_code", None)
export_has_data = isinstance(r, requests.Response) and code == 200 and len(r.text) > 100
record("GET /auth/me/export (staff, data-export feature)", "PASS" if export_has_data else "FAIL",
       f"status={code}, len={len(getattr(r, 'text', ''))}")

# ---------------------------------------------------------------------------
# 3b. NEW: admin verify-email endpoint (the actual code path added as the
#     fix for "no rescue path when SMTP isn't configured") -- exercised
#     directly, independent of whether the log-token-recovery path in
#     section 2 happened to find a token this run.
# ---------------------------------------------------------------------------
print("\n=== 3b. Admin verify-email endpoint (real rescue path) ===")
rescue_unique = uuid.uuid4().hex[:12]
rescue_email = f"basirah-audit-rescue-{rescue_unique}@example.com"
rescue_password = "AuditP@ssw0rd123"

rescue_reg = requests.Session()
r = call(rescue_reg, "POST", "/api/v1/auth/register",
         json={"email": rescue_email, "password": rescue_password, "full_name": "Audit Rescue Bot"})
code = getattr(r, "status_code", None)
rescue_user_id = None
if isinstance(r, requests.Response) and code == 201:
    rescue_user_id = r.json().get("id")
record("POST /auth/register (second throwaway user, for admin rescue test)",
       "PASS" if code == 201 and rescue_user_id else "FAIL", f"status={code}, id={rescue_user_id}")

if rescue_user_id:
    # Confirm the account is genuinely unverified and genuinely blocked
    # before the admin acts on it -- otherwise the "fix" test proves nothing.
    r = call(rescue_reg, "POST", "/api/v1/auth/login", json={"email": rescue_email, "password": rescue_password})
    code = getattr(r, "status_code", None)
    record("Login blocked before admin verifies (baseline)", "PASS" if code in (401, 403) else "FAIL",
           f"status={code}")

    r = call(staff, "POST", f"/api/v1/admin/users/{rescue_user_id}/verify-email", csrf=staff_csrf)
    code = getattr(r, "status_code", None)
    verified_flag = isinstance(r, requests.Response) and code == 200 and r.json().get("is_email_verified") is True
    record("POST /admin/users/{id}/verify-email (staff)", "PASS" if verified_flag else "FAIL",
           f"status={code}, body={getattr(r, 'text', '')[:300]}")

    r = call(rescue_reg, "POST", "/api/v1/auth/login", json={"email": rescue_email, "password": rescue_password})
    code = getattr(r, "status_code", None)
    record("Login succeeds after admin rescue verification (the actual fix, end to end)",
           "PASS" if code == 200 else "FAIL", f"status={code}")

    # Idempotency + audit trail sanity: calling it again on an already-
    # verified user should still succeed cleanly, not error.
    r = call(staff, "POST", f"/api/v1/admin/users/{rescue_user_id}/verify-email", csrf=staff_csrf)
    code = getattr(r, "status_code", None)
    record("POST /admin/users/{id}/verify-email is idempotent on an already-verified user",
           "PASS" if code == 200 else "FAIL", f"status={code}")

    # A non-staff caller must not be able to reach this route -- use the
    # rescue user's own now-authenticated (non-staff) session.
    r = call(rescue_reg, "POST", f"/api/v1/admin/users/{rescue_user_id}/verify-email")
    code = getattr(r, "status_code", None)
    record("POST /admin/users/{id}/verify-email rejects a non-staff caller",
           "PASS" if code in (401, 403) else "FAIL", f"status={code}")
else:
    record("Admin verify-email rescue-path test", "WARN", "skipped -- could not register the throwaway user")

# ---------------------------------------------------------------------------
# 4. Customer-facing surface, exercised as staff (auth-satisfied, sub-
#    scription-bypassed identically to how a paying customer would see it)
# ---------------------------------------------------------------------------
print("\n=== 4. Stock intelligence surface ===")
SYMBOLS = ["2222", "1120", "1180"]
for sym in SYMBOLS:
    for path in [f"/api/v1/stocks/{sym}", f"/api/v1/stocks/{sym}/quote", f"/api/v1/stocks/{sym}/history",
                 f"/api/v1/stocks/{sym}/technical", f"/api/v1/stocks/{sym}/fundamentals",
                 f"/api/v1/stocks/{sym}/decision", f"/api/v1/stocks/{sym}/decision-v2",
                 f"/api/v1/stocks/{sym}/analyst-report", f"/api/v1/stocks/{sym}/recommendation"]:
        r = call(staff, "GET", path)
        code = getattr(r, "status_code", None)
        record(f"GET {path}", "PASS" if code == 200 else "FAIL", f"status={code}")

r = call(staff, "GET", "/api/v1/stocks/search", params={"q": "ara"})
record("GET /stocks/search?q=ara", "PASS" if getattr(r, "status_code", None) == 200 else "FAIL",
       f"status={getattr(r, 'status_code', None)}")

# A symbol that does not exist should 404, not 500.
r = call(staff, "GET", "/api/v1/stocks/ZZZZZZZ/quote")
code = getattr(r, "status_code", None)
record("GET /stocks/ZZZZZZZ/quote (nonexistent symbol) -> 404, not 500", "PASS" if code == 404 else "FAIL",
       f"status={code}")

print("\n=== 5. Market intelligence surface ===")
for path in ["/api/v1/market/status", "/api/v1/market/summary", "/api/v1/market/rankings",
             "/api/v1/market/opportunities", "/api/v1/market/watchlists", "/api/v1/market/sectors",
             "/api/v1/market/alerts", "/api/v1/market/changes", "/api/v1/market/top-buy",
             "/api/v1/market/top-strong-buy"]:
    r = call(staff, "GET", path)
    code = getattr(r, "status_code", None)
    record(f"GET {path}", "PASS" if code == 200 else "FAIL", f"status={code}")

print("\n=== 6. News surface ===")
for path in ["/api/v1/news/market", "/api/v1/news/2222", "/api/v1/news/sources"]:
    r = call(staff, "GET", path)
    code = getattr(r, "status_code", None)
    record(f"GET {path}", "PASS" if code == 200 else "FAIL", f"status={code}")

print("\n=== 7. Portfolio surface (real analyze + every sub-resource) ===")
r = call(staff, "POST", "/api/v1/portfolio/analyze", csrf=staff_csrf,
         json={"name": "Audit Portfolio", "holdings": [{"symbol": "2222", "quantity": 10, "average_cost": 25.0},
                                                          {"symbol": "1120", "quantity": 5, "average_cost": 60.0}],
               "cash": 1000})
code = getattr(r, "status_code", None)
portfolio_id = None
if isinstance(r, requests.Response) and code == 200:
    portfolio_id = r.json().get("portfolio_id") or r.json().get("id")
record("POST /portfolio/analyze (real holdings)", "PASS" if code == 200 and portfolio_id else "FAIL",
       f"status={code}, portfolio_id={portfolio_id}")

if portfolio_id:
    for path in [f"/api/v1/portfolio/{portfolio_id}", f"/api/v1/portfolio/{portfolio_id}/recommendations",
                 f"/api/v1/portfolio/{portfolio_id}/risk", f"/api/v1/portfolio/{portfolio_id}/allocation",
                 f"/api/v1/portfolio/{portfolio_id}/diversification", f"/api/v1/portfolio/{portfolio_id}/rebalance",
                 f"/api/v1/portfolio/{portfolio_id}/health", f"/api/v1/portfolio/{portfolio_id}/news-alerts"]:
        r = call(staff, "GET", path)
        code = getattr(r, "status_code", None)
        record(f"GET {path}", "PASS" if code == 200 else "FAIL", f"status={code}")

# Requesting a portfolio that doesn't belong to us / doesn't exist -> 404, not 500 or 403 (leakage avoidance).
r = call(staff, "GET", "/api/v1/portfolio/999999999")
code = getattr(r, "status_code", None)
record("GET /portfolio/999999999 (nonexistent) -> 404", "PASS" if code == 404 else "FAIL", f"status={code}")

print("\n=== 8. Backtests surface (read-only probes only, no new run triggered) ===")
r = call(staff, "GET", "/api/v1/backtests/999999999")
code = getattr(r, "status_code", None)
record("GET /backtests/999999999 (nonexistent run) -> 404, not 500", "PASS" if code == 404 else "FAIL",
       f"status={code}")

print("\n=== 9. Admin surface (staff) ===")
for path in ["/api/v1/admin/system/health", "/api/v1/admin/system/summary", "/api/v1/admin/users",
             "/api/v1/admin/sessions", "/api/v1/admin/subscriptions", "/api/v1/admin/analytics",
             "/api/v1/admin/announcements", "/api/v1/admin/audit-log", "/api/v1/admin/feature-flags",
             "/api/v1/admin/usage/ai", "/api/v1/admin/ai-evolution/dashboard",
             "/api/v1/admin/ai-evolution/calibration-status", "/api/v1/admin/ai-evolution/patterns",
             "/api/v1/admin/ai-evolution/reflections", "/api/v1/admin/ai-evolution/paper-trade-comparison"]:
    r = call(staff, "GET", path)
    code = getattr(r, "status_code", None)
    record(f"GET {path} (staff)", "PASS" if code == 200 else "FAIL", f"status={code}")

print("\n=== 10. Real market scan trigger (POST /market/scan, the customer-path scan) ===")
r = call(staff, "POST", "/api/v1/market/scan", csrf=staff_csrf, json={})
code = getattr(r, "status_code", None)
record("POST /market/scan (staff)", "PASS" if code in (200, 202) else "FAIL", f"status={code}, body={getattr(r, 'text', '')[:300]}")
scan_run_id = None
if isinstance(r, requests.Response) and code in (200, 202):
    scan_run_id = r.json().get("id") or r.json().get("run_id")

if scan_run_id:
    time.sleep(20)
    r = call(staff, "GET", f"/api/v1/market/scan/{scan_run_id}")
    code = getattr(r, "status_code", None)
    status_val = r.json().get("status") if isinstance(r, requests.Response) and code == 200 else None
    record(f"GET /market/scan/{scan_run_id} reaches a terminal state", "PASS" if status_val in ("SUCCESS", "FAILED", "PARTIAL") else "WARN",
           f"status_field={status_val}")

print("\n=== 11. Broad crash-signature scan (unbiased -- not limited to previously-known bugs) ===")
logs = railway_logs()
if logs.startswith("__RAILWAY_LOGS_UNAVAILABLE__"):
    record("Fetch recent backend logs", "WARN", logs)
else:
    crash_patterns = [
        r"Traceback \(most recent call last\)",
        r"\bCRITICAL\b",
        r"Unhandled exception",
        r"psycopg2\.errors\.",
        r"sqlalchemy\.exc\.",
        r"\b500 Internal Server Error\b",
    ]
    found_any = False
    for pat in crash_patterns:
        matches = list(re.finditer(pat, logs))
        if matches:
            found_any = True
            # Print a little context around the first match for triage.
            idx = matches[0].start()
            context = logs[max(0, idx - 400):idx + 200]
            record(f"Crash pattern present in recent logs: {pat}", "WARN", f"{len(matches)} occurrence(s)")
            print(f"    --- context around first match of /{pat}/ ---")
            for line in context.splitlines()[-15:]:
                print(f"    {line}")
    if not found_any:
        record("No crash signatures (Traceback/CRITICAL/Unhandled/db-exceptions/500) in recent logs", "PASS")

# ---------------------------------------------------------------------------
print("\n=== SUMMARY ===")
fails = [r for r in results if r["status"] == "FAIL"]
warns = [r for r in results if r["status"] == "WARN"]
print(f"Total checks: {len(results)} | PASS: {len(results) - len(fails) - len(warns) - sum(1 for r in results if r['status'] == 'INFO')} "
      f"| FAIL: {len(fails)} | WARN: {len(warns)}")
if fails:
    print("\nFAILURES:")
    for f in fails:
        print(f" - {f['check']}: {f['detail']}")

print("\n=== FULL_RESULTS_JSON_START ===")
print(json.dumps(results, indent=2))
print("=== FULL_RESULTS_JSON_END ===")

sys.exit(1 if fails else 0)
