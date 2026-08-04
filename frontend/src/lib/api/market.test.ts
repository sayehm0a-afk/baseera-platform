import { afterEach, describe, expect, it, vi } from "vitest";
import { getMarketStatus, getMarketSummary, getRankings, triggerScan } from "./market";

/** market.ts is a direct, unmodified pass-through to the real backend
 * routes -- these tests prove the exact real data returned by the API
 * is what the caller gets back, with no local substitution, mock
 * fallback, or placeholder default value inserted on the frontend. */
describe("market API client", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("getMarketSummary returns the real backend payload unmodified", async () => {
    const realSummary = {
      scan_run_id: 42,
      generated_at: "2026-08-03T22:17:22Z",
      symbols_scanned: 3,
      bull_bear_ratio: 1.5,
      average_confidence: 71.2,
      average_recommendation_score: 63.0,
      buy_signal_count: 2,
      sell_signal_count: 0,
      strongest_sectors: ["Energy"],
      weakest_sectors: [],
      most_important_changes: [],
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify(realSummary), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const result = await getMarketSummary();

    expect(result).toEqual(realSummary);
    // No demo/placeholder value substitution: exactly what the backend sent.
    expect(result.symbols_scanned).toBe(3);
    const [, options] = fetchMock.mock.calls[0];
    expect(fetchMock.mock.calls[0][0]).toContain("/api/v1/market/summary");
    expect(options?.method ?? "GET").toBe("GET");
  });

  it("getMarketStatus returns the real backend session status unmodified", async () => {
    const realStatus = {
      status: "OPEN",
      label_ar: "السوق مفتوح",
      is_trading_day: true,
      server_time_riyadh: "2026-08-04T12:00:00+03:00",
      seconds_until_next_open: 0,
      seconds_until_close: 10800,
      last_completed_session_date: "2026-08-04",
      provider_connected: true,
      holiday_calendar_disclosed_gap: "لا يوجد تقويم للعطلات الرسمية...",
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify(realStatus), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const result = await getMarketStatus();

    expect(result).toEqual(realStatus);
    expect(fetchMock.mock.calls[0][0]).toContain("/api/v1/market/status");
  });

  it("getMarketSummary passes the run_id through as a real query param, not a synthesized one", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({}), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await getMarketSummary(42);

    expect(fetchMock.mock.calls[0][0]).toContain("/api/v1/market/summary?run_id=42");
  });

  it("getRankings surfaces a real, non-empty ranking list without inventing entries", async () => {
    const realRankings = {
      scan_run_id: 42,
      rankings: [
        {
          category: "TOP_BUY",
          entries: [
            { symbol: "2222", sector: "Energy", recommendation: "BUY", confidence: 82.5, final_score: 77.1, target_price: 34.2, expected_return_pct: 6.1, risk_level: "MEDIUM", rank_value: 1 },
          ],
          generated_at: "2026-08-03T22:17:22Z",
        },
      ],
    };
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(JSON.stringify(realRankings), { status: 200 }))
    );

    const result = await getRankings();

    expect(result.rankings).toHaveLength(1);
    expect(result.rankings[0].entries[0].symbol).toBe("2222");
    expect(result.rankings[0].entries[0].recommendation).not.toBe("DEMO");
  });

  it("triggerScan POSTs to the real scan endpoint and returns the real run row", async () => {
    const realRun = {
      id: 7, status: "PENDING", symbols_requested: 3, symbols_succeeded: 0,
      symbols_skipped: 0, symbols_failed: 0, error_summary: null,
      started_at: null, finished_at: null, duration_seconds: null,
      created_at: "2026-08-03T22:17:22Z",
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify(realRun), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const result = await triggerScan();

    expect(result).toEqual(realRun);
    expect(fetchMock.mock.calls[0][0]).toContain("/api/v1/market/scan");
    expect(fetchMock.mock.calls[0][1]?.method).toBe("POST");
  });
});
