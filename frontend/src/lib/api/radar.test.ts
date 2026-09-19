import { afterEach, describe, expect, it, vi } from "vitest";
import {
  getRadarHistoryDay,
  getRadarOpportunities,
  getRadarOpportunity,
  getRadarOpportunityBySymbol,
  getRadarSummary,
  triggerRadarScanNow,
} from "./radar";

/** radar.ts is a direct, unmodified pass-through to the real
 * consumer-facing /api/v1/radar/* routes, except
 * getRadarOpportunityBySymbol's own client-side find() (documented in
 * that function) -- these tests cover both the pass-through routes and
 * that one real piece of logic. */
describe("radar API client", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("getRadarSummary GETs the home summary route", async () => {
    const realSummary = { opportunities: [] };
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify(realSummary), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const result = await getRadarSummary();

    expect(result).toEqual(realSummary);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/radar/summary");
  });

  it("getRadarOpportunities encodes classification and limit as query params", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify([]), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await getRadarOpportunities({ classification: "STRONG_BUY_CANDIDATE", limit: 5 });

    const url = fetchMock.mock.calls[0][0] as string;
    expect(url).toContain("/api/v1/radar/opportunities?");
    expect(url).toContain("classification=STRONG_BUY_CANDIDATE");
    expect(url).toContain("limit=5");
  });

  it("getRadarOpportunities omits the query string entirely with no params", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify([]), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await getRadarOpportunities();

    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/radar/opportunities");
  });

  it("getRadarOpportunity GETs the specific opportunity's own URL", async () => {
    const realOpportunity = { id: 9, symbol: "2222" };
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify(realOpportunity), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const result = await getRadarOpportunity(9);

    expect(result).toEqual(realOpportunity);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/radar/opportunities/9");
  });

  it("getRadarOpportunityBySymbol returns the matching entry from the live list", async () => {
    const list = [
      { id: 1, symbol: "2222" },
      { id: 2, symbol: "1120" },
    ];
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify(list), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const result = await getRadarOpportunityBySymbol("1120");

    expect(result).toEqual({ id: 2, symbol: "1120" });
    expect(fetchMock.mock.calls[0][0]).toContain("limit=200");
  });

  it("getRadarOpportunityBySymbol resolves to null, never throws, when the symbol isn't live", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify([{ id: 1, symbol: "2222" }]), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const result = await getRadarOpportunityBySymbol("9999");

    expect(result).toBeNull();
  });

  it("getRadarHistoryDay encodes the date as a query param", async () => {
    const realDay = { date: "2026-09-01", opportunities: [] };
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify(realDay), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const result = await getRadarHistoryDay("2026-09-01");

    expect(result).toEqual(realDay);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/radar/history?date=2026-09-01");
  });

  it("triggerRadarScanNow POSTs to the scan-now route", async () => {
    const realResult = { run_id: 3 };
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify(realResult), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const result = await triggerRadarScanNow();

    expect(result).toEqual(realResult);
    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/radar/scan-now");
    expect(options.method).toBe("POST");
  });
});
