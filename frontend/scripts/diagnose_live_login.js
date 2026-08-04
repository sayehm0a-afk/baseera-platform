"use strict";

/**
 * Diagnostic (not pass/fail) real-browser run: captures everything
 * that could explain "the automated check passed but a real user's
 * browser still shows the login error" -- console errors, every
 * network request/response during the attempt, the exact visible
 * error text, and screenshots. Never logs STAFF_EMAIL/STAFF_PASSWORD
 * or any cookie/token value.
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

const consoleLog = [];
const networkLog = [];

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();

  page.on("console", (msg) => {
    consoleLog.push(`[console.${msg.type()}] ${msg.text()}`);
  });
  page.on("pageerror", (err) => {
    consoleLog.push(`[pageerror] ${err.message}\n${err.stack || ""}`);
  });
  page.on("requestfailed", (req) => {
    networkLog.push(`[requestfailed] ${req.method()} ${req.url()} -- ${req.failure()?.errorText}`);
  });
  page.on("response", (res) => {
    networkLog.push(`[response] ${res.status()} ${res.request().method()} ${res.url()}`);
  });

  try {
    console.log(`Navigating to ${FRONTEND_URL}/login`);
    await page.goto(`${FRONTEND_URL}/login`, { waitUntil: "networkidle" });
    await page.screenshot({ path: path.join(EVIDENCE_DIR, "1-login-page-loaded.png"), fullPage: true });

    await page.fill('input[type="email"]', STAFF_EMAIL);
    await page.fill('input[type="password"]', STAFF_PASSWORD);
    await page.click('button[type="submit"]');

    // Wait for EITHER a navigation to /dashboard OR the error banner to
    // appear -- whichever happens first, don't assume success.
    const outcome = await Promise.race([
      page.waitForURL("**/dashboard", { timeout: 15000 }).then(() => "navigated_to_dashboard"),
      page
        .waitForSelector('[role="alert"]', { timeout: 15000 })
        .then(() => "error_banner_shown"),
    ]).catch(() => "timeout_neither_happened");

    console.log(`\nOUTCOME: ${outcome}`);
    console.log(`Current URL: ${page.url()}`);

    const alertEl = await page.$('[role="alert"]');
    if (alertEl) {
      const alertText = await alertEl.textContent();
      console.log(`Visible error banner text: ${alertText}`);
    } else {
      console.log("No [role=alert] element present.");
    }

    await page.screenshot({ path: path.join(EVIDENCE_DIR, "2-after-submit.png"), fullPage: true });

    console.log("\n=== Console log (page + page errors) ===");
    console.log(consoleLog.join("\n") || "(empty)");

    console.log("\n=== Network log (all requests/responses during this run) ===");
    console.log(networkLog.join("\n"));

    fs.writeFileSync(path.join(EVIDENCE_DIR, "console.log"), consoleLog.join("\n"));
    fs.writeFileSync(path.join(EVIDENCE_DIR, "network.log"), networkLog.join("\n"));

    // Specifically isolate the auth-related network activity.
    console.log("\n=== Auth-endpoint responses only ===");
    console.log(networkLog.filter((l) => l.includes("/api/v1/auth/")).join("\n") || "(none observed)");
  } catch (err) {
    console.error("Diagnostic script itself errored:", err);
    await page.screenshot({ path: path.join(EVIDENCE_DIR, "SCRIPT-ERROR.png"), fullPage: true }).catch(() => {});
    process.exitCode = 1;
  } finally {
    await browser.close();
  }
})();
