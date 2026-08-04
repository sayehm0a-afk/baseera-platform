/**
 * Temporary, evidence-only verification script for Phase 1 (Decision
 * Engine V2) against the real production frontend/backend, using the
 * real OWNER account. Runs under WebKit (Safari engine) at an iPhone
 * viewport, per the Phase 1 spec's real-browser Safari/WebKit + mobile
 * requirement. Checks:
 *   1. Login works under WebKit/mobile viewport, Arabic RTL intact.
 *   2. GET /api/v1/stocks/{symbol}/decision-v2 returns a real,
 *      gate-checked decision (analysis_version, decision taxonomy,
 *      confidence disclaimer, at least one gate record).
 *   3. The stock analysis page renders the executive decision card
 *      (decision label, confidence disclaimer text) and no
 *      unexpected page overflow at the mobile viewport width.
 *   4. Arabic search normalization: a hamza-less query ("ارامكو")
 *      still finds the real hamza-form stored name ("أرامكو").
 *   5. Owner panel shows the new Phase 1 fields (engine version,
 *      market status label, STRICT_REAL_DATA status) for a real
 *      OWNER account.
 *   6. GET /api/v1/market/status returns one of the 9 real
 *      MarketSessionStatus values.
 * Deleted immediately after this evidence is captured -- no lasting
 * change to the app.
 */
const { webkit, devices } = require("playwright");

const FRONTEND_URL = process.env.FRONTEND_URL;
const BACKEND_URL = process.env.BACKEND_URL;
const EMAIL = process.env.STAFF_EMAIL;
const PASSWORD = process.env.STAFF_PASSWORD;
const SYMBOL = process.env.VERIFY_SYMBOL || "2222";

const VALID_MARKET_STATUSES = new Set([
  "OPEN", "PRE_MARKET", "PRE_OPEN_AUCTION", "CLOSING_AUCTION", "CLOSING_PRICE_TRADING",
  "POST_CLOSE", "WEEKEND", "CLOSED", "UNKNOWN",
]);
const VALID_DECISIONS = new Set([
  "STRONG_BUY_CANDIDATE", "BUY_CANDIDATE", "WAIT_FOR_ENTRY", "WATCH",
  "HOLD", "REDUCE", "EXIT", "REJECT", "INSUFFICIENT_DATA",
]);

async function main() {
  const browser = await webkit.launch();
  const context = await browser.newContext({ ...devices["iPhone 13"] });
  const page = await context.newPage();
  const results = { browser_engine: "webkit", device: "iPhone 13" };

  await page.goto(`${FRONTEND_URL}/login`, { waitUntil: "networkidle" });
  results.login_page_dir = await page.evaluate(() => document.documentElement.getAttribute("dir"));

  await page.fill('input[type="email"]', EMAIL);
  await page.fill('input[type="password"]', PASSWORD);
  await Promise.all([
    page.waitForURL(/\/dashboard/, { timeout: 20000 }),
    page.click('button[type="submit"]'),
  ]);
  results.reached_dashboard = page.url().includes("/dashboard");

  // --- 1. Decision Engine V2 API, direct fetch ---------------------------
  const decisionV2Resp = await page.evaluate(async ({ backendUrl, symbol }) => {
    const res = await fetch(`${backendUrl}/api/v1/stocks/${symbol}/decision-v2`, { credentials: "include" });
    const body = await res.json().catch(() => null);
    return { status: res.status, body };
  }, { backendUrl: BACKEND_URL, symbol: SYMBOL });
  results.decision_v2_api_status = decisionV2Resp.status;
  const d = decisionV2Resp.body || {};
  results.decision_v2_symbol = d.symbol;
  results.decision_v2_decision = d.decision;
  results.decision_v2_decision_is_valid_enum = VALID_DECISIONS.has(d.decision);
  results.decision_v2_analysis_version = d.analysis_version;
  results.decision_v2_confidence_disclaimer_ar = d.confidence_disclaimer_ar;
  results.decision_v2_analysis_disclaimer_ar_present = !!d.analysis_disclaimer_ar;
  results.decision_v2_gates_count = Array.isArray(d.gates) ? d.gates.length : null;
  results.decision_v2_sub_scores_present = !!d.sub_scores;
  results.decision_v2_data_source = d.data_source;
  results.decision_v2_market_status = d.market_status;

  // --- 2. Stock analysis page renders the executive decision card --------
  const consoleErrors = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });
  page.on("pageerror", (err) => consoleErrors.push(`pageerror: ${err.message}`));

  await page.goto(`${FRONTEND_URL}/stocks/${SYMBOL}`, { waitUntil: "networkidle" });
  await page.waitForTimeout(2500);
  const pageText = await page.evaluate(() => document.body.innerText);
  results.stock_page_text_length = pageText.length;
  results.stock_page_text_snippet = pageText.slice(0, 800);
  results.stock_page_has_decision_label = !!d.decision_label_ar && pageText.includes(d.decision_label_ar);
  results.stock_page_has_confidence_disclaimer = pageText.includes(
    "درجة الثقة تقيس قوة وتوافق الأدلة المتاحة"
  );
  results.stock_page_has_analysis_disclaimer = pageText.includes(
    "هذا تحليل آلي مساعد مبني على البيانات المتاحة"
  );
  results.stock_page_has_english_leak = /REAL DATA UNAVAILABLE|Unclassified/.test(pageText);
  results.stock_page_console_errors = consoleErrors.slice(0, 10);
  const overflowCheck = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
  results.mobile_horizontal_overflow_px = overflowCheck.scrollWidth - overflowCheck.clientWidth;

  // --- 3. Arabic search normalization (hamza-less query) ------------------
  const searchDiag = await page.evaluate(async (backendUrl) => {
    async function doSearch(q) {
      const res = await fetch(`${backendUrl}/api/v1/stocks/search?q=${encodeURIComponent(q)}`, {
        credentials: "include",
      });
      const body = await res.json().catch(() => null);
      return { status: res.status, body };
    }
    return {
      by_symbol: await doSearch("2222"),
      by_hamza_form: await doSearch("أرامكو"),
      by_no_hamza: await doSearch("ارامكو"),
    };
  }, BACKEND_URL);
  results.search_by_symbol_2222 = searchDiag.by_symbol.body;
  results.search_by_hamza_form_results = searchDiag.by_hamza_form.body
    ? searchDiag.by_hamza_form.body.results
    : null;
  results.search_by_no_hamza_results = searchDiag.by_no_hamza.body
    ? searchDiag.by_no_hamza.body.results
    : null;
  results.arabic_search_status = searchDiag.by_no_hamza.status;
  results.arabic_search_result_count = searchDiag.by_no_hamza.body
    ? searchDiag.by_no_hamza.body.results.length
    : null;
  results.arabic_search_found_hamza_form = !!(
    searchDiag.by_no_hamza.body &&
    searchDiag.by_no_hamza.body.results.some((r) => r.name_ar && r.name_ar.includes("أ"))
  );

  // --- 4. Owner panel Phase 1 additions -----------------------------------
  const adminSummaryDiag = await page.evaluate(async (backendUrl) => {
    const res = await fetch(`${backendUrl}/api/v1/admin/system/summary`, { credentials: "include" });
    const body = await res.json().catch((e) => ({ parse_error: String(e) }));
    return { status: res.status, body };
  }, BACKEND_URL);
  results.admin_summary_api_status = adminSummaryDiag.status;
  results.admin_summary_decision_engine_version = adminSummaryDiag.body
    ? adminSummaryDiag.body.decision_engine_version
    : null;
  results.admin_summary_market_status_label_ar = adminSummaryDiag.body
    ? adminSummaryDiag.body.market_status_label_ar
    : null;
  results.admin_summary_strict_real_data_enforced = adminSummaryDiag.body
    ? adminSummaryDiag.body.strict_real_data_enforced
    : null;
  results.admin_summary_full_body_when_error = adminSummaryDiag.status !== 200 ? adminSummaryDiag.body : null;

  await page.goto(`${FRONTEND_URL}/owner`, { waitUntil: "networkidle" });
  await page.waitForTimeout(2500);
  const ownerText = await page.evaluate(() => document.body.innerText);
  results.owner_page_text_length = ownerText.length;
  results.owner_page_text_snippet = ownerText.slice(0, 800);
  results.owner_page_reachable = page.url().includes("/owner") && !page.url().includes("/dashboard");
  results.owner_page_has_engine_version = ownerText.includes("2.0.0");
  results.owner_page_has_market_status_row = ownerText.includes("حالة السوق الآن");
  results.owner_page_has_strict_real_data_row = ownerText.includes("STRICT_REAL_DATA");

  // --- 5. Market status API -------------------------------------------------
  const marketStatusResp = await page.evaluate(async (backendUrl) => {
    const res = await fetch(`${backendUrl}/api/v1/market/status`, { credentials: "include" });
    const body = await res.json().catch(() => null);
    return { status: res.status, body };
  }, BACKEND_URL);
  results.market_status_api_status = marketStatusResp.status;
  results.market_status_value = marketStatusResp.body ? marketStatusResp.body.status : null;
  results.market_status_value_is_valid_enum = VALID_MARKET_STATUSES.has(results.market_status_value);

  console.log("VERIFICATION_RESULTS_JSON_START");
  console.log(JSON.stringify(results, null, 2));
  console.log("VERIFICATION_RESULTS_JSON_END");

  await browser.close();
}

main().catch((err) => {
  console.error("VERIFICATION_FAILED:", err.message);
  process.exit(1);
});
