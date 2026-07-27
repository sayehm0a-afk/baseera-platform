import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiFetch } from "./client";

describe("apiFetch", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
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
