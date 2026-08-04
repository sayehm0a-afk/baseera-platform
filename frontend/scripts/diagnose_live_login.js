"use strict";

/**
 * Diagnostic (not pass/fail) real-browser run: captures everything
 * that could explain "the automated check passed once but a real
 * user's browser (and a later automated re-check) still shows the
 * login error" -- console errors, every network request/response,
 * the exact visible error text (outerHTML, not just textContent, in
 * case of a timing read), input field values right after fill (proves
 * whether React's controlled state actually received them -- a classic
 * Next.js hydration-race symptom if not), and repeats the whole
 * attempt twice with different pre-submit waits to check whether
 * timing changes the outcome. Never logs STAFF_EMAIL/STAFF_PASSWORD or
 * any cookie/token value.
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

const EVIDENCE_DIR = path.join(__dirname, "..", "live-login-evidence");
fs.mkdirSync(EVIDENCE_DIR, { recursive: true });

async function attempt(browser, label, preSubmitWaitMs) {
  console.log(`\n\n########## ATTEMPT: ${label} (pre-submit wait ${preSubmitWaitMs}ms) ##########`);
  const consoleLog = [];
  const networkLog = [];
  const context = await browser.newContext();
  const page = await context.newPage();

  page.on("console", (msg) => consoleLog.push(`[console.${msg.type()}] ${msg.text()}`));
  page.on("pageerror", (err) => consoleLog.push(`[pageerror] ${err.message}\n${err.stack || ""}`));
  page.on("requestfailed", (req) => networkLog.push(`[requestfailed] ${req.method()} ${req.url()} -- ${req.failure()?.errorText}`));
  page.on("response", (res) => networkLog.push(`[response] ${res.status()} ${res.request().method()} ${res.url()}`));

  try {
    await page.goto(`${FRONTEND_URL}/login`, { waitUntil: "networkidle" });
    await page.screenshot({ path: path.join(EVIDENCE_DIR, `${label}-1-loaded.png`), fullPage: true });

    if (preSubmitWaitMs > 0) {
      await page.waitForTimeout(preSubmitWaitMs);
    }

    await page.fill('input[type="email"]', STAFF_EMAIL);
    await page.fill('input[type="password"]', STAFF_PASSWORD);

    const emailValueLen = await page.inputValue('input[type="email"]').then((v) => v.length);
    const passwordValueLen = await page.inputValue('input[type="password"]').then((v) => v.length);
    console.log(`Input field values right before click -- email length: ${emailValueLen}, password length: ${passwordValueLen} (expected: ${STAFF_EMAIL.length}, ${STAFF_PASSWORD.length})`);

    await page.click('button[type="submit"]');

    // IMPORTANT: '[role="alert"]' alone also matches Next.js's own
    // #__next-route-announcer__ (a permanently-present, visually-hidden
    // accessibility div with role="alert" on every App Router page --
    // confirmed by run 30913094187, which matched it in ~50ms, before
    // any real network round-trip could complete). The login page's
    // actual error banner is specifically a <p role="alert"> -- exclude
    // the announcer explicitly so this can't false-positive again.
    const REAL_ERROR_SELECTOR = 'p[role="alert"]';
    const outcome = await Promise.race([
      page.waitForURL("**/dashboard", { timeout: 20000 }).then(() => "navigated_to_dashboard"),
      page.waitForSelector(REAL_ERROR_SELECTOR, { timeout: 20000 }).then(() => "error_banner_shown"),
    ]).catch(() => "timeout_neither_happened");

    console.log(`OUTCOME: ${outcome}`);
    console.log(`Current URL: ${page.url()}`);

    await page.waitForTimeout(300);
    const alertEl = await page.$(REAL_ERROR_SELECTOR);
    if (alertEl) {
      const outerHtml = await alertEl.evaluate((el) => el.outerHTML);
      console.log(`Real error banner (p[role=alert]) outerHTML: ${outerHtml}`);
    } else {
      console.log("No p[role=alert] element present (the real login error banner did not appear).");
    }

    await page.screenshot({ path: path.join(EVIDENCE_DIR, `${label}-2-after-submit.png`), fullPage: true });

    console.log(`--- Console log (${label}) ---`);
    console.log(consoleLog.join("\n") || "(empty)");

    console.log(`--- Auth-endpoint network activity (${label}) ---`);
    console.log(networkLog.filter((l) => l.includes("/api/v1/auth/")).join("\n") || "(none observed)");

    fs.writeFileSync(path.join(EVIDENCE_DIR, `${label}-console.log`), consoleLog.join("\n"));
    fs.writeFileSync(path.join(EVIDENCE_DIR, `${label}-network.log`), networkLog.join("\n"));

    return outcome;
  } finally {
    await context.close();
  }
}

(async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const results = {};
    results.immediate = await attempt(browser, "immediate", 0);
    results.after_2s_wait = await attempt(browser, "after-2s-wait", 2000);

    console.log("\n\n########## SUMMARY ##########");
    console.log(JSON.stringify(results, null, 2));
  } catch (err) {
    console.error("Diagnostic script itself errored:", err);
    process.exitCode = 1;
  } finally {
    await browser.close();
  }
})();
