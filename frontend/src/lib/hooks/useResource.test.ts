import { renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/client";
import { useResource } from "./useResource";

describe("useResource", () => {
  it("starts in loading state", () => {
    const { result } = renderHook(() => useResource("2222", () => new Promise(() => {})));
    expect(result.current).toEqual({ status: "loading" });
  });

  it("resolves to ready with the fetched data", async () => {
    const { result } = renderHook(() => useResource("2222", async (key) => ({ symbol: key })));
    await waitFor(() => expect(result.current.status).toBe("ready"));
    expect(result.current).toMatchObject({ status: "ready", data: { symbol: "2222" } });
  });

  it("classifies a stock_not_found ApiError as not_found", async () => {
    const fetcher = vi.fn(async () => {
      throw new ApiError(404, "stock_not_found", "No such stock.");
    });
    const { result } = renderHook(() => useResource("XXXX", fetcher));
    await waitFor(() => expect(result.current.status).toBe("not_found"));
  });

  it("classifies an insufficient_data ApiError as insufficient_data", async () => {
    const fetcher = vi.fn(async () => {
      throw new ApiError(422, "insufficient_data", "Not enough history.");
    });
    const { result } = renderHook(() => useResource("2222", fetcher));
    await waitFor(() => expect(result.current.status).toBe("insufficient_data"));
  });

  it("classifies a provider_unavailable ApiError as unavailable", async () => {
    const fetcher = vi.fn(async () => {
      throw new ApiError(503, "provider_unavailable", "SAHMK is down.");
    });
    const { result } = renderHook(() => useResource("2222", fetcher));
    await waitFor(() => expect(result.current.status).toBe("unavailable"));
  });

  it("classifies any other ApiError code, and any non-ApiError throw, as a generic error", async () => {
    const fetcher = vi.fn(async () => {
      throw new ApiError(422, "invalid_symbol_format", "Bad symbol.");
    });
    const { result } = renderHook(() => useResource("2222", fetcher));
    await waitFor(() => expect(result.current.status).toBe("error"));

    const networkFailure = vi.fn(async () => {
      throw new TypeError("Failed to fetch");
    });
    const { result: result2 } = renderHook(() => useResource("2222", networkFailure));
    await waitFor(() => expect(result2.current.status).toBe("error"));
  });

  it("re-fetches when the key changes, and never applies a stale response", async () => {
    let resolveFirst: (value: { symbol: string }) => void = () => {};
    const firstPromise = new Promise<{ symbol: string }>((resolve) => {
      resolveFirst = resolve;
    });
    const fetcher = vi
      .fn()
      .mockImplementationOnce(() => firstPromise)
      .mockImplementationOnce(async (key: string) => ({ symbol: key }));

    const { result, rerender } = renderHook(({ symbol }) => useResource(symbol, fetcher), {
      initialProps: { symbol: "2222" },
    });

    rerender({ symbol: "1120" });
    await waitFor(() => expect(result.current.status).toBe("ready"));
    expect(result.current).toMatchObject({ status: "ready", data: { symbol: "1120" } });

    // The stale "2222" fetch resolves after the key already moved on --
    // it must never overwrite the current "1120" result.
    resolveFirst({ symbol: "2222" });
    await new Promise((r) => setTimeout(r, 10));
    expect(result.current).toMatchObject({ status: "ready", data: { symbol: "1120" } });
  });
});
