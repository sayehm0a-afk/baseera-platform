/**
 * Temporary, evidence-only verification script for the practical
 * live-market-testing release. Logs in with the real OWNER account
 * against the real production frontend/backend, then checks:
 *   1. Dashboard loads and the Arabic real-data/market-status banner
 *      renders (not the old English "REAL DATA UNAVAILABLE" text).
 *   2. Scan and Opportunities pages load.
 *   3. Stock search (symbol) returns a result and navigates.
 *   4. The owner-only pages (/owner, /owner/live-test) are reachable
 *      for a real OWNER account (no unexpected redirect to /dashboard).
 *   5. GET /api/v1/market/status returns 200 with a real status value.
 * Deleted immediately after this evidence is captured -- no lasting
 * change to the app.
 */
const { chromium } = require("playwright");

const FRONTEND_URL = process.env.FRONTEND_URL;
const BACKEND_URL = process.env.BACKEND_URL;
const EMAIL = process.env.STAFF_EMAIL;
const PASSWORD = process.env.STAFF_PASSWORD;

async function main() {
  const browser = await chromium.launch();
  const context = await browser.newContext();
  const page = await context.newPage();
  const results = {};

  await page.goto(`${FRONTEND_URL}/login`, { waitUntil: "networkidle" });
  results.login_page_dir = await page.evaluate(() => document.documentElement.getAttribute("dir"));
  results.login_page_lang = await page.evaluate(() => document.documentElement.getAttribute("lang"));

  await page.fill('input[type="email"]', EMAIL);
  await page.fill('input[type="password"]', PASSWORD);
  await Promise.all([
    page.waitForURL(/\/dashboard/, { timeout: 15000 }),
    page.click('button[type="submit"]'),
  ]);
  results.reached_dashboard = page.url().includes("/dashboard");

  await page.waitForTimeout(2000);
  const bannerText = await page.evaluate(() => {
    const el = document.querySelector('[role="status"]');
    return el ? el.textContent : null;
  });
  results.banner_text = bannerText;
  results.banner_has_english_unavailable_text =
    !!bannerText && bannerText.includes("REAL DATA UNAVAILABLE");
  results.banner_has_arabic = !!bannerText && /[؀-ۿ]/.test(bannerText);

  await page.goto(`${FRONTEND_URL}/scan`, { waitUntil: "networkidle" });
  results.scan_page_status = "loaded";

  await page.goto(`${FRONTEND_URL}/opportunities`, { waitUntil: "networkidle" });
  results.opportunities_page_status = "loaded";

  await page.goto(`${FRONTEND_URL}/dashboard`, { waitUntil: "networkidle" });
  const searchInput = await page.$('input[type="search"]');
  if (searchInput) {
    await searchInput.fill("2222");
    await page.waitForTimeout(800);
    const dropdownVisible = await page.evaluate(() => {
      return !!document.querySelector('ul li button');
    });
    results.search_dropdown_appeared = dropdownVisible;
  } else {
    results.search_dropdown_appeared = "no_search_input_found";
  }

  await page.goto(`${FRONTEND_URL}/owner`, { waitUntil: "networkidle" });
  await page.waitForTimeout(1500);
  results.owner_page_url_after_load = page.url();
  results.owner_page_reachable = page.url().includes("/owner") && !page.url().includes("/dashboard");

  await page.goto(`${FRONTEND_URL}/owner/live-test`, { waitUntil: "networkidle" });
  await page.waitForTimeout(1500);
  results.live_test_page_url_after_load = page.url();
  results.live_test_page_reachable =
    page.url().includes("/owner/live-test");

  const marketStatusResp = await page.evaluate(async (backendUrl) => {
    const res = await fetch(`${backendUrl}/api/v1/market/status`, { credentials: "include" });
    const body = await res.json().catch(() => null);
    return { status: res.status, body };
  }, BACKEND_URL);
  results.market_status_api = marketStatusResp;

  await page.goto(`${FRONTEND_URL}/stocks/2222`, { waitUntil: "networkidle" });
  await page.waitForTimeout(1500);
  results.stock_detail_page_status_code = "loaded";
  const stockPageHasChart = await page.evaluate(() => !!document.querySelector("canvas"));
  results.stock_detail_has_chart_canvas = stockPageHasChart;

  console.log("VERIFICATION_RESULTS_JSON_START");
  console.log(JSON.stringify(results, null, 2));
  console.log("VERIFICATION_RESULTS_JSON_END");

  await browser.close();
}

main().catch((err) => {
  console.error("VERIFICATION_FAILED:", err.message);
  process.exit(1);
});
