"use strict";

/**
 * Real-browser (headless Chromium) verification that the SameSite/CSRF
 * cookie fix (see src/api/routes/auth.py, main.py, frontend/src/lib/
 * api/client.ts) actually works end-to-end against the real deployed
 * production frontend/backend -- not a curl simulation, which doesn't
 * enforce the SameSite/CORS browser policies that caused the original
 * bug in the first place.
 *
 * Never logs STAFF_EMAIL/STAFF_PASSWORD or any cookie/token value --
 * only HTTP status codes and URLs are printed.
 *
 * Exits non-zero (and dumps a diagnostic) on any assertion failure.
 */

const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const FRONTEND_URL = process.env.FRONTEND_URL;
const STAFF_EMAIL = process.env.STAFF_EMAIL;
const STAFF_PASSWORD = process.env.STAFF_PASSWORD;

if (!FRONTEND_URL || !STAFF_EMAIL || !STAFF_PASSWORD) {
  console.error("FRONTEND_URL, STAFF_EMAIL, and STAFF_PASSWORD must all be set.");
  process.exit(1);
}

const EVIDENCE_DIR = path.join(__dirname, "..", "browser-login-evidence");
fs.mkdirSync(EVIDENCE_DIR, { recursive: true });

const authResponses = [];
let backendUrl = null;
let lastCsrfTokenHeader = null;

function recordResponse(response) {
  const url = response.url();
  if (url.includes("/api/v1/auth/")) {
    const path = new URL(url).pathname;
    authResponses.push({ path, status: response.status() });
    const csrfHeader = response.headers()["x-csrf-token"];
    if (csrfHeader) {
      lastCsrfTokenHeader = csrfHeader;
    }
    if (!backendUrl) {
      backendUrl = new URL(url).origin;
    }
  }
}

function statusFor(pathSuffix) {
  const matches = authResponses.filter((r) => r.path.endsWith(pathSuffix));
  return matches.length ? matches[matches.length - 1].status : null;
}

function assert(condition, message) {
  if (!condition) {
    console.error(`ASSERTION FAILED: ${message}`);
    console.error("Auth-endpoint responses observed so far:", JSON.stringify(authResponses, null, 2));
    process.exitCode = 1;
    throw new Error(message);
  }
  console.log(`OK: ${message}`);
}

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();
  page.on("response", recordResponse);

  try {
    console.log(`Navigating to ${FRONTEND_URL}/login`);
    await page.goto(`${FRONTEND_URL}/login`, { waitUntil: "networkidle" });

    await page.fill('input[type="email"]', STAFF_EMAIL);
    await page.fill('input[type="password"]', STAFF_PASSWORD);
    await page.click('button[type="submit"]');

    await page.waitForURL("**/dashboard", { timeout: 15000 });
    await page.waitForLoadState("networkidle");
    await page.screenshot({ path: path.join(EVIDENCE_DIR, "1-dashboard-after-login.png"), fullPage: true });

    assert(page.url().endsWith("/dashboard"), "Browser login redirected to /dashboard (not bounced back to /login)");
    assert(statusFor("/auth/login") === 200, "POST /api/v1/auth/login returned 200");
    assert(statusFor("/auth/me") === 200, "GET /api/v1/auth/me returned 200 immediately after login (proves the browser sent the session cookies cross-site)");

    // --- Reload: the in-memory CSRF token from login is gone; /auth/me
    // must still work purely from the persisted cookies, and must
    // re-supply the CSRF token via its own X-CSRF-Token response header.
    authResponses.length = 0;
    await page.reload({ waitUntil: "networkidle" });
    assert(page.url().endsWith("/dashboard"), "Session survives a page reload (still on /dashboard, not bounced to /login)");
    assert(statusFor("/auth/me") === 200, "GET /api/v1/auth/me returned 200 after reload");
    assert(!!lastCsrfTokenHeader, "X-CSRF-Token response header was present (cross-origin CSRF hand-off working)");

    // --- Refresh: exercise the real refresh endpoint using the exact
    // cookies this real browser context is currently holding, and the
    // CSRF token captured from a real response header (the same
    // hand-off apiFetch itself relies on) -- proves the browser will
    // actually deliver the SameSite=None cookies on a fresh POST, and
    // that the server accepts the CSRF token this way.
    const refreshResult = await page.evaluate(
      async ({ backendUrl, csrfToken }) => {
        const res = await fetch(`${backendUrl}/api/v1/auth/refresh`, {
          method: "POST",
          credentials: "include",
          headers: { "X-CSRF-Token": csrfToken },
        });
        return res.status;
      },
      { backendUrl, csrfToken: lastCsrfTokenHeader }
    );
    assert(refreshResult === 200, `POST /api/v1/auth/refresh returned 200 (got ${refreshResult})`);

    // --- Logout via the real UI.
    await page.goto(`${FRONTEND_URL}/settings`, { waitUntil: "networkidle" });
    assert(page.url().endsWith("/settings"), "Settings page (a protected route) loaded without bouncing to /login");

    await page.click("text=تسجيل الخروج");
    await page.waitForURL("**/login", { timeout: 15000 });
    await page.screenshot({ path: path.join(EVIDENCE_DIR, "2-after-logout.png"), fullPage: true });
    assert(page.url().endsWith("/login"), "Logout redirected to /login");

    const cookiesAfterLogout = await context.cookies();
    const sessionCookieNames = cookiesAfterLogout
      .filter((c) => ["access_token", "refresh_token", "csrf_token"].includes(c.name))
      .map((c) => c.name);
    assert(sessionCookieNames.length === 0, `Session cookies were cleared after logout (remaining: ${sessionCookieNames.join(", ") || "none"})`);

    // --- Confirm the protected dashboard is no longer reachable.
    authResponses.length = 0;
    await page.goto(`${FRONTEND_URL}/dashboard`, { waitUntil: "networkidle" });
    await page.waitForURL("**/login", { timeout: 15000 });
    assert(page.url().endsWith("/login"), "Dashboard is no longer reachable after logout (redirected back to /login)");

    console.log("\nALL BROWSER-LOGIN ASSERTIONS PASSED.");
  } catch (err) {
    await page.screenshot({ path: path.join(EVIDENCE_DIR, "FAILURE.png"), fullPage: true }).catch(() => {});
    console.error(err);
    process.exitCode = 1;
  } finally {
    await browser.close();
  }

  if (process.exitCode === 1) {
    process.exit(1);
  }
})();
