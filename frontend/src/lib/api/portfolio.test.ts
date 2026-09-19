import { afterEach, describe, expect, it, vi } from "vitest";
import {
  addPortfolioHolding,
  analyzePortfolio,
  createPortfolio,
  deletePortfolio,
  deletePortfolioHolding,
  getPortfolioHoldings,
  listMyPortfolios,
  updatePortfolioHolding,
} from "./portfolio";

/** portfolio.ts is a direct, unmodified pass-through to the real
 * backend routes -- these tests prove the exact URL/method/body sent
 * and that the real response comes back unmodified, with no local
 * allocation/risk/rebalance logic re-derived on the frontend. */
describe("portfolio API client", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("analyzePortfolio POSTs the request body and returns the real analysis unmodified", async () => {
    const realAnalysis = { portfolio_id: 1, name: "محفظتي", total_value: 1000 };
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify(realAnalysis), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const body = {
      name: "محفظتي",
      holdings: [{ symbol: "2222", quantity: 10, average_cost: 30 }],
      cash: 500,
    };
    const result = await analyzePortfolio(body);

    expect(result).toEqual(realAnalysis);
    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/portfolio/analyze");
    expect(options.method).toBe("POST");
    expect(JSON.parse(options.body)).toEqual(body);
  });

  it("listMyPortfolios GETs the collection route", async () => {
    const realList = { portfolios: [{ id: 1, name: "محفظتي" }] };
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify(realList), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const result = await listMyPortfolios();

    expect(result).toEqual(realList);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/portfolio");
  });

  it("createPortfolio POSTs the create body", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ id: 1 }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await createPortfolio({ name: "محفظة جديدة", cash_balance: 1000 });

    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/portfolio");
    expect(options.method).toBe("POST");
    expect(JSON.parse(options.body)).toEqual({ name: "محفظة جديدة", cash_balance: 1000 });
  });

  it("deletePortfolio issues a DELETE to the portfolio's own URL", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ message: "تم" }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await deletePortfolio(7);

    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/portfolio/7");
    expect(options.method).toBe("DELETE");
  });

  it("getPortfolioHoldings GETs the real holdings for the given portfolio id", async () => {
    const realHoldings = { portfolio_id: 3, holdings: [] };
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify(realHoldings), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const result = await getPortfolioHoldings(3);

    expect(result).toEqual(realHoldings);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/portfolio/3/holdings");
  });

  it("addPortfolioHolding POSTs to the holdings sub-collection", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ id: 5 }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await addPortfolioHolding(3, { symbol: "2222", quantity: 10, average_cost: 30 });

    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/portfolio/3/holdings");
    expect(options.method).toBe("POST");
    expect(JSON.parse(options.body)).toEqual({ symbol: "2222", quantity: 10, average_cost: 30 });
  });

  it("updatePortfolioHolding PATCHes the specific holding's own URL", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ id: 5 }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await updatePortfolioHolding(3, 5, { quantity: 20 });

    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/portfolio/3/holdings/5");
    expect(options.method).toBe("PATCH");
    expect(JSON.parse(options.body)).toEqual({ quantity: 20 });
  });

  it("deletePortfolioHolding DELETEs the specific holding's own URL", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ message: "تم" }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await deletePortfolioHolding(3, 5);

    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/portfolio/3/holdings/5");
    expect(options.method).toBe("DELETE");
  });
});
