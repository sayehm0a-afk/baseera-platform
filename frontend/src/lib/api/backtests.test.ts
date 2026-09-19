import { afterEach, describe, expect, it, vi } from "vitest";
import { cancelBacktest, createBacktest, getBacktest, getBacktestMetrics } from "./backtests";

/** backtests.ts is a direct, unmodified pass-through to the real
 * backend routes -- these tests prove the exact URL/method/body sent
 * and that the real response comes back unmodified, with no strategy/
 * metrics logic re-derived on the frontend. */
describe("backtests API client", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("createBacktest POSTs the create request body", async () => {
    const realRun = { id: 1, status: "PENDING" };
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify(realRun), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const body = { symbols: ["2222"], start_date: "2026-01-01", end_date: "2026-06-01" };
    const result = await createBacktest(body);

    expect(result).toEqual(realRun);
    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/backtests");
    expect(options.method).toBe("POST");
    expect(JSON.parse(options.body)).toEqual(body);
  });

  it("getBacktest GETs the specific run's own URL", async () => {
    const realRun = { id: 1, status: "SUCCESS" };
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify(realRun), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const result = await getBacktest(1);

    expect(result).toEqual(realRun);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/backtests/1");
  });

  it("getBacktestMetrics GETs the run's metrics sub-route", async () => {
    const realMetrics = { id: 1, status: "SUCCESS", metrics: { overall: {} } };
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify(realMetrics), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const result = await getBacktestMetrics(1);

    expect(result).toEqual(realMetrics);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/backtests/1/metrics");
  });

  it("cancelBacktest POSTs to the run's cancel sub-route", async () => {
    const realRun = { id: 1, status: "FAILED" };
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify(realRun), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const result = await cancelBacktest(1);

    expect(result).toEqual(realRun);
    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/backtests/1/cancel");
    expect(options.method).toBe("POST");
  });
});
