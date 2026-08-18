import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import StocksDirectoryPage from "./page";
import type { StockDirectory, StockDirectoryItem } from "@/lib/api/stocks-types";

/** GET /api/v1/stocks/directory reads only already-persisted PriceBar
 * rows (see that route's own docstring) -- this page never triggers a
 * live SAHMK call. The 300ms search debounce is exercised with fake
 * timers rather than real waits. */

vi.mock("@/lib/api/stocks", () => ({
  getStockDirectory: vi.fn(),
}));

import { getStockDirectory } from "@/lib/api/stocks";

function item(overrides: Partial<StockDirectoryItem> = {}): StockDirectoryItem {
  return {
    symbol: "2222",
    name_en: "Saudi Aramco",
    name_ar: "أرامكو السعودية",
    sector: "Energy",
    sector_ar: "الطاقة",
    current_price: 30.5,
    change_amount: 0.5,
    change_pct: 1.67,
    price_as_of: "2026-08-17T00:00:00Z",
    freshness_label_ar: "آخر جلسة",
    ...overrides,
  };
}

function directory(overrides: Partial<StockDirectory> = {}): StockDirectory {
  return { total: 1, limit: 30, offset: 0, results: [item()], ...overrides };
}

describe("StocksDirectoryPage", () => {
  beforeEach(() => {
    vi.mocked(getStockDirectory).mockReset();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  async function flushDebounce() {
    await act(async () => {
      await vi.advanceTimersByTimeAsync(300);
    });
  }

  /** Flushes pending microtasks (e.g. a mocked fetch's `.then`) without
   * relying on RTL's `findBy*` polling, which uses real timers and never
   * fires while fake timers are installed. */
  async function flushMicrotasks() {
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
  }

  it("loads and shows real directory rows on mount", async () => {
    vi.mocked(getStockDirectory).mockResolvedValue(directory());

    render(<StocksDirectoryPage />);
    await flushDebounce();

    expect(screen.getByText("أرامكو السعودية")).toBeInTheDocument();
    expect(screen.getByText("2222 · الطاقة")).toBeInTheDocument();
    expect(getStockDirectory).toHaveBeenCalledWith({ q: undefined, limit: 30, offset: 0 });
  });

  it("shows the honest empty state for no results, never a fabricated row", async () => {
    vi.mocked(getStockDirectory).mockResolvedValue(directory({ total: 0, results: [] }));

    render(<StocksDirectoryPage />);
    await flushDebounce();

    expect(screen.getByText("لا توجد نتائج")).toBeInTheDocument();
  });

  it("debounces the search query before calling the API again", async () => {
    vi.mocked(getStockDirectory).mockResolvedValue(directory());
    render(<StocksDirectoryPage />);
    await flushDebounce();
    vi.mocked(getStockDirectory).mockClear();

    const input = screen.getByPlaceholderText("ابحث برمز السهم أو اسم الشركة...");
    fireEvent.change(input, { target: { value: "ارامكو" } });

    // Not yet called -- still within the debounce window.
    expect(getStockDirectory).not.toHaveBeenCalled();

    await flushDebounce();
    expect(getStockDirectory).toHaveBeenCalledWith({ q: "ارامكو", limit: 30, offset: 0 });
  });

  it("shows a load-more control only when more results exist, and appends on click", async () => {
    vi.mocked(getStockDirectory).mockResolvedValueOnce(
      directory({ total: 2, results: [item({ symbol: "2222" })] })
    );
    render(<StocksDirectoryPage />);
    await flushDebounce();

    const loadMore = screen.getByText("تحميل المزيد");
    vi.mocked(getStockDirectory).mockResolvedValueOnce(
      directory({ total: 2, offset: 1, results: [item({ symbol: "1120", name_ar: "الراجحي" })] })
    );

    fireEvent.click(loadMore);
    await flushMicrotasks();

    expect(screen.getByText("الراجحي")).toBeInTheDocument();
    expect(screen.getByText("أرامكو السعودية")).toBeInTheDocument();
    expect(screen.queryByText("تحميل المزيد")).not.toBeInTheDocument();
  });

  it("shows the error state when the request fails, not a silently empty list", async () => {
    vi.mocked(getStockDirectory).mockRejectedValue(new Error("network error"));

    render(<StocksDirectoryPage />);
    await flushDebounce();

    expect(screen.getByText("تعذّر تحميل قائمة الأسهم")).toBeInTheDocument();
  });
});
