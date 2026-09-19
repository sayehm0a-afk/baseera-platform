import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AddHoldingForm } from "./AddHoldingForm";

vi.mock("@/lib/api/stocks", () => ({
  searchStocks: vi.fn(),
}));

import { searchStocks } from "@/lib/api/stocks";

describe("AddHoldingForm", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.clearAllMocks();
  });

  it("rejects an empty symbol or non-positive quantity before calling onAdd", async () => {
    const onAdd = vi.fn();
    render(<AddHoldingForm onAdd={onAdd} />);

    fireEvent.click(screen.getByText("إضافة"));

    expect(await screen.findByText("أدخل رمز السهم وكمية أكبر من صفر.")).toBeInTheDocument();
    expect(onAdd).not.toHaveBeenCalled();
  });

  it("submits a valid holding with an omitted average cost as undefined, not zero", async () => {
    const onAdd = vi.fn().mockResolvedValue(undefined);
    render(<AddHoldingForm onAdd={onAdd} />);

    fireEvent.change(screen.getByPlaceholderText("رمز السهم أو اسم الشركة"), {
      target: { value: "2222" },
    });
    fireEvent.change(screen.getByPlaceholderText("الكمية"), { target: { value: "10" } });
    fireEvent.click(screen.getByText("إضافة"));

    await waitFor(() => expect(onAdd).toHaveBeenCalledWith("2222", 10, undefined));
  });

  it("clears the form after a successful add", async () => {
    const onAdd = vi.fn().mockResolvedValue(undefined);
    render(<AddHoldingForm onAdd={onAdd} />);

    const symbolInput = screen.getByPlaceholderText("رمز السهم أو اسم الشركة") as HTMLInputElement;
    fireEvent.change(symbolInput, { target: { value: "2222" } });
    fireEvent.change(screen.getByPlaceholderText("الكمية"), { target: { value: "10" } });
    fireEvent.click(screen.getByText("إضافة"));

    await waitFor(() => expect(symbolInput.value).toBe(""));
  });

  it("surfaces the real backend error message on failure, not a generic one", async () => {
    const onAdd = vi.fn().mockRejectedValue(new Error("السهم غير موجود في القائمة."));
    render(<AddHoldingForm onAdd={onAdd} />);

    fireEvent.change(screen.getByPlaceholderText("رمز السهم أو اسم الشركة"), {
      target: { value: "9999" },
    });
    fireEvent.change(screen.getByPlaceholderText("الكمية"), { target: { value: "1" } });
    fireEvent.click(screen.getByText("إضافة"));

    expect(await screen.findByText("السهم غير موجود في القائمة.")).toBeInTheDocument();
  });

  it("shows real search suggestions and fills the symbol field on pick", async () => {
    vi.useFakeTimers();
    vi.mocked(searchStocks).mockResolvedValue({
      query: "راجحي",
      results: [
        { symbol: "1120", name_ar: "الراجحي", name_en: "Al Rajhi Bank", sector: null, sector_ar: null },
      ],
    });

    render(<AddHoldingForm onAdd={vi.fn()} />);
    const symbolInput = screen.getByPlaceholderText("رمز السهم أو اسم الشركة") as HTMLInputElement;
    fireEvent.change(symbolInput, { target: { value: "راجحي" } });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(200);
    });

    expect(screen.getByText("الراجحي")).toBeInTheDocument();
    fireEvent.click(screen.getByText("الراجحي"));

    expect(symbolInput.value).toBe("1120");
  });
});
