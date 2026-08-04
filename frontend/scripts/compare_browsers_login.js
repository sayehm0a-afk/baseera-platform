"use strict";

/**
 * Reproduces the login flow on WebKit (Playwright's closest available
 * approximation of Safari/iOS Safari -- there is no real iOS Safari
 * binary available to run headlessly; WebKit's engine, including its
 * Intelligent Tracking Prevention cookie behavior, is the same family)
 * using an iPhone device emulation profile (viewport, user agent,
 * touch), side by side with Chromium, against the real production
 * frontend/backend. Captures full request/response and cookie-state
 * evidence for both so any browser-specific incompatibility is visible
 * in the raw evidence, not inferred. Never logs STAFF_EMAIL/
 * STAFF_PASSWORD or any cookie/token value.
 */

const playwright = require("playwright");
const fs = require("fs");
const path = require("path");

const FRONTEND_URL = process.env.FRONTEND_URL;
const STAFF_EMAIL = process.env.STAFF_EMAIL;
const STAFF_PASSWORD = process.env.STAFF_PASSWORD;

if (!FRONTEND_URL || !STAFF_EMAIL || !STAFF_PASSWORD) {
  console.error("FRONTEND_URL, STAFF_EMAIL, and STAFF_PASSWORD must all be set.");
  process.exit(1);
}

const EVIDENCE_DIR = path.join(__dirname, "..", "browser-comparison-evidence");
fs.mkdirSync(EVIDENCE_DIR, { recursive: true });

const REAL_ERROR_SELECTOR = 'p[role="alert"]';

async function runOn(engineName, contextOptions) {
  console.log(`\n\n########## ENGINE: ${engineName} ##########`);
  const consoleLog = [];
  const networkLog = [];
  const browserType = playwright[engineName];
  const browser = await browserType.launch({ headless: true });
  const context = await browser.newContext(contextOptions);
  const page = await context.newPage();

  page.on("console", (msg) => consoleLog.push(`[console.${msg.type()}] ${msg.text()}`));
  page.on("pageerror", (err) => consoleLog.push(`[pageerror] ${err.message}`));
  page.on("requestfailed", (req) => networkLog.push(`[requestfailed] ${req.method()} ${req.url()} -- ${req.failure()?.errorText}`));
  page.on("response", async (res) => {
    let setCookieCount = 0;
    try {
      const headers = res.headers();
      // Playwright's headers() folds repeated headers into one
      // comma-joined string for most, but Set-Cookie is kept via
      // headersArray() for multi-value correctness on some engines --
      // just record presence/count here, never values.
      const all = await res.headersArray();
      setCookieCount = all.filter((h) => h.name.toLowerCase() === "set-cookie").length;
      void headers;
    } catch {
      // best-effort only
    }
    const line = `[response] ${res.status()} ${res.request().method()} ${res.url()}${setCookieCount ? ` (Set-Cookie x${setCookieCount})` : ""}`;
    networkLog.push(line);
  });

  const result = { engine: engineName, steps: {} };

  try {
    await page.goto(`${FRONTEND_URL}/login`, { waitUntil: "networkidle" });
    await page.screenshot({ path: path.join(EVIDENCE_DIR, `${engineName}-1-login-page.png`), fullPage: true });

    await page.fill('input[type="email"]', STAFF_EMAIL);
    await page.fill('input[type="password"]', STAFF_PASSWORD);
    await page.click('button[type="submit"]');

    const outcome = await Promise.race([
      page.waitForURL("**/dashboard", { timeout: 20000 }).then(() => "navigated_to_dashboard"),
      page.waitForSelector(REAL_ERROR_SELECTOR, { timeout: 20000 }).then(() => "error_banner_shown"),
    ]).catch(() => "timeout_neither_happened");

    result.steps.loginOutcome = outcome;
    result.steps.urlAfterLogin = page.url();

    if (outcome === "error_banner_shown") {
      await page.waitForTimeout(300);
      const alertEl = await page.$(REAL_ERROR_SELECTOR);
      result.steps.errorBannerText = alertEl ? await alertEl.textContent() : null;
    }

    await page.screenshot({ path: path.join(EVIDENCE_DIR, `${engineName}-2-after-login.png`), fullPage: true });

    // Cookie state as Playwright's own context sees it right now --
    // this reflects what the ENGINE actually stored/kept, which is the
    // real question here (names + attributes only, never values).
    const cookies = await context.cookies();
    result.steps.cookiesAfterLogin = cookies.map((c) => ({
      name: c.name,
      domain: c.domain,
      path: c.path,
      sameSite: c.sameSite,
      secure: c.secure,
      httpOnly: c.httpOnly,
    }));

    // Now reload -- the real second-order test: does the session
    // survive purely on stored cookies being re-sent, exactly what a
    // user closing/reopening the app or refreshing would hit.
    await page.reload({ waitUntil: "networkidle" });
    result.steps.urlAfterReload = page.url();
    result.steps.sessionSurvivedReload = page.url().endsWith("/dashboard");

    result.steps.authNetworkActivity = networkLog.filter((l) => l.includes("/api/v1/auth/"));
    result.steps.consoleLog = consoleLog;

    fs.writeFileSync(path.join(EVIDENCE_DIR, `${engineName}-network.log`), networkLog.join("\n"));
    fs.writeFileSync(path.join(EVIDENCE_DIR, `${engineName}-console.log`), consoleLog.join("\n"));

    console.log(JSON.stringify(result, null, 2));
    return result;
  } catch (err) {
    console.error(`${engineName} run errored:`, err);
    await page.screenshot({ path: path.join(EVIDENCE_DIR, `${engineName}-ERROR.png`), fullPage: true }).catch(() => {});
    result.steps.scriptError = String(err);
    return result;
  } finally {
    await browser.close();
  }
}

(async () => {
  const iphone = playwright.devices["iPhone 14"];
  console.log(`WebKit context will emulate: ${iphone.userAgent}`);

  const chromiumResult = await runOn("chromium", {});
  const webkitResult = await runOn("webkit", iphone);

  console.log("\n\n########## COMPARISON SUMMARY ##########");
  console.log(JSON.stringify({ chromium: chromiumResult.steps, webkit: webkitResult.steps }, null, 2));

  const bothSucceeded =
    chromiumResult.steps.loginOutcome === "navigated_to_dashboard" &&
    webkitResult.steps.loginOutcome === "navigated_to_dashboard";
  console.log(`\nBoth engines reached /dashboard: ${bothSucceeded}`);
  if (!bothSucceeded) {
    console.log("::warning::Browser-specific incompatibility detected -- see COMPARISON SUMMARY above.");
  }
})();
