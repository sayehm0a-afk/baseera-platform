import { afterEach, describe, expect, it, vi } from "vitest";
import {
  addToWatchlist,
  getMyWatchlist,
  getWatchlistNewsAlerts,
  refreshWatchlistNewsAlerts,
  removeFromWatchlist,
} from "./watchlist";

/** watchlist.ts is a direct, unmodified pass-through to the real
 * backend routes -- these tests prove the exact URL/method/body sent
 * and that the real response comes back unmodified. */
describe("watchlist API client", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("getMyWatchlist GETs the user's own saved symbols", async () => {
    const realWatchlist = { items: [{ symbol: "2222" }] };
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify(realWatchlist), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const result = await getMyWatchlist();

    expect(result).toEqual(realWatchlist);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/watchlist");
  });

  it("addToWatchlist POSTs the symbol in the request body", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ symbol: "2222" }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await addToWatchlist("2222");

    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/watchlist/items");
    expect(options.method).toBe("POST");
    expect(JSON.parse(options.body)).toEqual({ symbol: "2222" });
  });

  it("removeFromWatchlist DELETEs the symbol's own item URL", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ message: "تم" }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await removeFromWatchlist("2222");

    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/watchlist/items/2222");
    expect(options.method).toBe("DELETE");
  });

  it("getWatchlistNewsAlerts GETs the already-persisted alerts", async () => {
    const realAlerts = { alerts: [] };
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify(realAlerts), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const result = await getWatchlistNewsAlerts();

    expect(result).toEqual(realAlerts);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/watchlist/news-alerts");
  });

  it("refreshWatchlistNewsAlerts POSTs to the refresh sub-route", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ alerts: [] }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await refreshWatchlistNewsAlerts();

    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/watchlist/news-alerts/refresh");
    expect(options.method).toBe("POST");
  });
});
