import { afterEach, describe, expect, it, vi } from "vitest";
import { searchStocks } from "./stocks";

/** stocks.ts's searchStocks is a direct pass-through to the real
 * GET /api/v1/stocks/search route -- no client-side symbol/name
 * matching or fabricated results. */
describe("searchStocks", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("returns the real backend search results unmodified", async () => {
    const realResults = {
      query: "أرامكو",
      results: [{ symbol: "2222", name_en: "Saudi Aramco", name_ar: "أرامكو السعودية", sector: "Energy" }],
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify(realResults), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const result = await searchStocks("أرامكو");

    expect(result).toEqual(realResults);
    const url = fetchMock.mock.calls[0][0] as string;
    expect(url).toContain("/api/v1/stocks/search?");
    expect(decodeURIComponent(url)).toContain("q=أرامكو");
  });

  it("passes a custom limit through as a real query param", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ query: "2", results: [] }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await searchStocks("2", 5);

    expect(fetchMock.mock.calls[0][0]).toContain("limit=5");
  });
});
