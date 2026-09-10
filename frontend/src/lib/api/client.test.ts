import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiFetch } from "./client";

describe("apiFetch", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    document.cookie = "csrf_token=; expires=Thu, 01 Jan 1970 00:00:00 GMT";
  });

  it("returns the parsed JSON body on success", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ hello: "world" }), { status: 200 })
      )
    );

    const result = await apiFetch<{ hello: string }>("/api/v1/whatever");
    expect(result).toEqual({ hello: "world" });
  });

  it("keeps authenticated browser requests on the frontend origin", async () => {
    const fetchMock = vi.fn().mockImplementation(async () =>
      new Response(JSON.stringify({}), { status: 200 })
    );
    vi.stubGlobal("fetch", fetchMock);

    await apiFetch("/api/v1/auth/me");
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/auth/me");
    await apiFetch("/health/market-data");
    expect(fetchMock.mock.calls[1][0]).toBe("/health/market-data");
  });

  it("throws a typed ApiError using the backend's error envelope", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            error: { code: "no_market_scan_data", message: "No scan yet." },
          }),
          { status: 404 }
        )
      )
    );

    await expect(apiFetch("/api/v1/market/summary")).rejects.toMatchObject({
      code: "no_market_scan_data",
      status: 404,
    });
  });

  it("ApiError is an instance of Error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("not json", { status: 500 }))
    );

    try {
      await apiFetch("/api/v1/whatever");
      expect.unreachable();
    } catch (error) {
      expect(error).toBeInstanceOf(ApiError);
    }
  });

  it("sends credentials and the CSRF header read from the csrf_token cookie", async () => {
    document.cookie = "csrf_token=the-real-token";
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({}), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await apiFetch("/api/v1/whatever");

    const [, init] = fetchMock.mock.calls[0];
    expect(init.credentials).toBe("include");
    expect(init.headers["X-CSRF-Token"]).toBe("the-real-token");

    document.cookie = "csrf_token=; expires=Thu, 01 Jan 1970 00:00:00 GMT";
  });

  it("uses the current cookie after another tab rotates it, even if an older response header was captured", async () => {
    document.cookie = "csrf_token=token-from-response-header";
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({}), {
          status: 200,
          headers: { "X-CSRF-Token": "token-from-response-header" },
        })
      )
      .mockResolvedValueOnce(new Response(JSON.stringify({}), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await apiFetch("/api/v1/auth/login", { method: "POST" });
    // A different tab refreshes the shared session cookie. This tab's
    // last response header is now stale, but document.cookie is current.
    document.cookie = "csrf_token=rotated-in-another-tab";
    await apiFetch("/api/v1/portfolios");

    const [, secondInit] = fetchMock.mock.calls[1];
    expect(secondInit.headers["X-CSRF-Token"]).toBe("rotated-in-another-tab");

    document.cookie = "csrf_token=; expires=Thu, 01 Jan 1970 00:00:00 GMT";
  });

  it("recovers an expired access token after a reload using the surviving CSRF cookie", async () => {
    // Fresh module = no in-memory state, like returning to Safari tomorrow.
    vi.resetModules();
    const { apiFetch: freshFetch } = await import("./client");
    document.cookie = "csrf_token=surviving-csrf";
    const fetchMock = vi.fn().mockImplementation(async (path, init) => {
      if (path.endsWith("/auth/refresh")) {
        expect(init.headers["X-CSRF-Token"]).toBe("surviving-csrf");
        document.cookie = "csrf_token=rotated-csrf";
        return new Response(JSON.stringify({ message: "ok" }), { status: 200 });
      }
      if (fetchMock.mock.calls.length === 1) {
        return new Response("expired", { status: 401 });
      }
      expect(init.headers["X-CSRF-Token"]).toBe("rotated-csrf");
      return new Response(JSON.stringify({ id: 1 }), { status: 200 });
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(freshFetch("/api/v1/auth/me")).resolves.toEqual({ id: 1 });
    expect(fetchMock).toHaveBeenCalledTimes(3);
    document.cookie = "csrf_token=; expires=Thu, 01 Jan 1970 00:00:00 GMT";
  });

  it("silently refreshes once and retries after a 401 on a non-bootstrap path", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response("unauthenticated", { status: 401 })) // original request
      .mockResolvedValueOnce(new Response(JSON.stringify({}), { status: 200 })) // /auth/refresh
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ ok: true }), { status: 200 })
      ); // retried original request
    vi.stubGlobal("fetch", fetchMock);

    const result = await apiFetch<{ ok: boolean }>("/api/v1/portfolios");

    expect(result).toEqual({ ok: true });
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(fetchMock.mock.calls[1][0]).toContain("/api/v1/auth/refresh");
  });

  it("does not attempt a refresh-and-retry for a 401 on /api/v1/auth/login", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({ error: { code: "invalid_credentials", message: "no" } }),
        { status: 401 }
      )
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      apiFetch("/api/v1/auth/login", { method: "POST" })
    ).rejects.toMatchObject({ code: "invalid_credentials" });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("serializes the refresh network call across tabs via navigator.locks, never letting two overlap", async () => {
    // A real queue-based fake, not a stub that just calls the callback
    // immediately -- otherwise this test would pass regardless of
    // whether performRefresh() actually uses the lock at all.
    let queue: Promise<unknown> = Promise.resolve();
    const lockRequest = vi.fn((_name: string, callback: () => Promise<unknown>) => {
      const result = queue.then(callback);
      queue = result.catch(() => undefined);
      return result;
    });
    vi.stubGlobal("navigator", { locks: { request: lockRequest } });

    let activeRefreshes = 0;
    let maxObservedOverlap = 0;
    const fetchMock = vi.fn().mockImplementation(async (path: string) => {
      if (path === "/api/v1/auth/refresh") {
        activeRefreshes += 1;
        maxObservedOverlap = Math.max(maxObservedOverlap, activeRefreshes);
        await new Promise((resolve) => setTimeout(resolve, 5));
        activeRefreshes -= 1;
        return new Response(JSON.stringify({}), { status: 200 });
      }
      return new Response("unauthenticated", { status: 401 });
    });
    vi.stubGlobal("fetch", fetchMock);

    // Two "tabs": fresh module instances so each has its own
    // module-scoped refreshInFlight, sharing only the global
    // navigator.locks fake above -- exactly like two real browser tabs
    // sharing the OS-level Web Locks manager.
    vi.resetModules();
    const tabA = await import("./client");
    vi.resetModules();
    const tabB = await import("./client");

    await Promise.all([
      tabA.apiFetch("/api/v1/portfolios").catch(() => undefined),
      tabB.apiFetch("/api/v1/watchlist").catch(() => undefined),
    ]);

    expect(lockRequest).toHaveBeenCalledTimes(2);
    expect(lockRequest.mock.calls[0][0]).toBe("basirah-auth-refresh");
    expect(maxObservedOverlap).toBe(1);
  });

  it("negative control: without navigator.locks, two tabs' refresh calls DO overlap -- proving the lock test above is meaningful", async () => {
    vi.stubGlobal("navigator", {});

    let activeRefreshes = 0;
    let maxObservedOverlap = 0;
    const fetchMock = vi.fn().mockImplementation(async (path: string) => {
      if (path === "/api/v1/auth/refresh") {
        activeRefreshes += 1;
        maxObservedOverlap = Math.max(maxObservedOverlap, activeRefreshes);
        await new Promise((resolve) => setTimeout(resolve, 5));
        activeRefreshes -= 1;
        return new Response(JSON.stringify({}), { status: 200 });
      }
      return new Response("unauthenticated", { status: 401 });
    });
    vi.stubGlobal("fetch", fetchMock);

    vi.resetModules();
    const tabA = await import("./client");
    vi.resetModules();
    const tabB = await import("./client");

    await Promise.all([
      tabA.apiFetch("/api/v1/portfolios").catch(() => undefined),
      tabB.apiFetch("/api/v1/watchlist").catch(() => undefined),
    ]);

    expect(maxObservedOverlap).toBe(2);
  });

  it("gives up and surfaces the original error when the refresh attempt itself fails", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ error: { code: "unauthenticated", message: "no" } }),
          { status: 401 }
        )
      ) // original request
      .mockResolvedValueOnce(new Response("still unauthenticated", { status: 401 })); // /auth/refresh fails too
    vi.stubGlobal("fetch", fetchMock);

    await expect(apiFetch("/api/v1/portfolios")).rejects.toMatchObject({
      code: "unauthenticated",
    });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
