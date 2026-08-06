"""Independent frontend audit: drives the real production frontend
with a headless browser exactly as a human would -- typing into the
real login form, clicking through real navigation -- capturing
console errors, failed network requests, and a screenshot per screen
as evidence. Throwaway audit tooling, not application code.
"""

import json
import os
import sys

from playwright.sync_api import sync_playwright

FRONTEND_URL = os.environ["FRONTEND_URL"].rstrip("/")
STAFF_EMAIL = os.environ["STAFF_EMAIL"]
STAFF_PASSWORD = os.environ["STAFF_PASSWORD"]
SCREENSHOT_DIR = os.environ.get("SCREENSHOT_DIR", "/tmp/screenshots")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

results = []


def record(check, status, detail=""):
    results.append({"check": check, "status": status, "detail": detail})
    marker = {"PASS": "OK", "FAIL": "**FAIL**", "INFO": "info", "WARN": "WARN"}[status]
    print(f"[{marker}] {check}" + (f" -- {detail}" if detail else ""))


def visit(page, path, name, console_errors, failed_requests):
    console_errors.clear()
    failed_requests.clear()
    url = f"{FRONTEND_URL}{path}"
    try:
        resp = page.goto(url, wait_until="networkidle", timeout=30000)
    except Exception as exc:  # noqa: BLE001 -- record any navigation failure as evidence, not a crash
        record(f"Navigate to {path} ({name})", "FAIL", f"exception: {exc}")
        return
    page.wait_for_timeout(1500)
    shot_path = os.path.join(SCREENSHOT_DIR, f"{name}.png")
    page.screenshot(path=shot_path, full_page=True)
    code = resp.status if resp else None
    ok = code is not None and code < 400
    detail = f"http={code}, console_errors={len(console_errors)}, failed_requests={len(failed_requests)}"
    record(f"Load {path} ({name})", "PASS" if ok and not console_errors and not failed_requests else "WARN" if ok else "FAIL", detail)
    if console_errors:
        for e in console_errors[:5]:
            print(f"    console error: {e}")
    if failed_requests:
        for fr in failed_requests[:5]:
            print(f"    failed request: {fr}")


with sync_playwright() as p:
    browser = p.chromium.launch()
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    page = context.new_page()

    console_errors = []
    failed_requests = []
    page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
    page.on("requestfailed", lambda req: failed_requests.append(f"{req.method} {req.url} -- {req.failure}"))
    page.on("response", lambda resp: failed_requests.append(f"{resp.status} {resp.url}") if resp.status >= 500 else None)

    # --- Public pages, unauthenticated ---
    visit(page, "/", "00_root", console_errors, failed_requests)
    visit(page, "/login", "01_login", console_errors, failed_requests)
    visit(page, "/register", "02_register", console_errors, failed_requests)

    # --- Real login through the actual UI form (not the API directly) ---
    console_errors.clear()
    failed_requests.clear()
    page.goto(f"{FRONTEND_URL}/login", wait_until="networkidle", timeout=30000)
    try:
        page.fill('input[type="email"], input[name="email"]', STAFF_EMAIL)
        page.fill('input[type="password"], input[name="password"]', STAFF_PASSWORD)
        page.click('button[type="submit"]')
        page.wait_for_load_state("networkidle", timeout=15000)
        page.wait_for_timeout(1500)
    except Exception as exc:  # noqa: BLE001
        record("Log in through the real UI form", "FAIL", f"could not complete login flow: {exc}")
    else:
        landed_on_dashboard = "/login" not in page.url
        record("Log in through the real UI form", "PASS" if landed_on_dashboard else "FAIL",
               f"landed at {page.url}, console_errors={len(console_errors)}")
        shot_path = os.path.join(SCREENSHOT_DIR, "03_post_login.png")
        page.screenshot(path=shot_path, full_page=True)

    # --- Every authenticated customer-facing screen ---
    screens = [
        ("/dashboard", "10_dashboard"),
        ("/scan", "11_scan"),
        ("/watchlist", "12_watchlist"),
        ("/opportunities", "13_opportunities"),
        ("/portfolio", "14_portfolio"),
        ("/ai", "15_ai"),
        ("/news", "16_news"),
        ("/reports", "17_reports"),
        ("/strategies", "18_strategies"),
        ("/settings", "19_settings"),
        ("/stocks/2222", "20_stock_detail_2222"),
        ("/owner", "21_owner_panel"),
    ]
    for path, name in screens:
        visit(page, path, name, console_errors, failed_requests)

    browser.close()

print("\n=== SUMMARY ===")
fails = [r for r in results if r["status"] == "FAIL"]
warns = [r for r in results if r["status"] == "WARN"]
print(f"Total checks: {len(results)} | FAIL: {len(fails)} | WARN: {len(warns)}")

print("\n=== FULL_RESULTS_JSON_START ===")
print(json.dumps(results, indent=2))
print("=== FULL_RESULTS_JSON_END ===")

sys.exit(1 if fails else 0)
