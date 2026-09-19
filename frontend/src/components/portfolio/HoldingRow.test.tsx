import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { HoldingRow } from "./HoldingRow";
import type { PortfolioHoldingDetail } from "@/lib/api/portfolio-types";

function holding(overrides: Partial<PortfolioHoldingDetail> = {}): PortfolioHoldingDetail {
  return {
    id: 1,
    symbol: "2222",
    name_ar: "أرامكو السعودية",
    name_en: "Saudi Aramco",
    sector: "Energy",
    sector_ar: "الطاقة",
    currency: "SAR",
    quantity: 100,
    average_cost: 30,
    current_price: 33.5,
    price_as_of: "2026-09-19T00:00:00Z",
    freshness_label_ar: "آخر جلسة",
    invested_cost: 3000,
    current_value: 3350,
    unrealized_pnl: 350,
    unrealized_pnl_pct: 11.67,
    guidance_decision: null,
    guidance_label_ar: null,
    guidance_basis_ar: null,
    guidance_confidence: null,
    guidance_evaluated_at: null,
    guidance_freshness_status: null,
    is_guidance_fresh: null,
    ...overrides,
  };
}

describe("HoldingRow", () => {
  it("renders quantity, price, and a signed P&L percentage", () => {
    render(<HoldingRow holding={holding()} onUpdate={vi.fn()} onDelete={vi.fn()} />);

    expect(screen.getByText(/100 × 30\.00/)).toBeInTheDocument();
    expect(screen.getByText(/350\.00 \(\+11\.67%\)/)).toBeInTheDocument();
  });

  it("falls back to an em dash for a holding with no persisted price, never a fabricated value", () => {
    render(
      <HoldingRow
        holding={holding({
          current_price: null,
          current_value: null,
          unrealized_pnl: null,
          unrealized_pnl_pct: null,
        })}
        onUpdate={vi.fn()}
        onDelete={vi.fn()}
      />
    );

    expect(screen.getByText("السعر الحالي").parentElement).toHaveTextContent("—");
    expect(screen.getByText(/— \(—\)/)).toBeInTheDocument();
  });

  it("rejects a zero/negative quantity in the inline edit form before calling onUpdate", async () => {
    const onUpdate = vi.fn();
    render(<HoldingRow holding={holding()} onUpdate={onUpdate} onDelete={vi.fn()} />);

    fireEvent.click(screen.getByText("تعديل"));
    fireEvent.change(screen.getByPlaceholderText("الكمية"), { target: { value: "0" } });
    fireEvent.click(screen.getByText("حفظ"));

    expect(await screen.findByText("الكمية يجب أن تكون أكبر من صفر.")).toBeInTheDocument();
    expect(onUpdate).not.toHaveBeenCalled();
  });

  it("saves a valid edit and shows an error if the save itself fails", async () => {
    const onUpdate = vi.fn().mockRejectedValue(new Error("network error"));
    render(<HoldingRow holding={holding()} onUpdate={onUpdate} onDelete={vi.fn()} />);

    fireEvent.click(screen.getByText("تعديل"));
    fireEvent.change(screen.getByPlaceholderText("الكمية"), { target: { value: "50" } });
    fireEvent.click(screen.getByText("حفظ"));

    expect(onUpdate).toHaveBeenCalledWith(50, 30);
    expect(await screen.findByText("تعذّر حفظ التعديل. حاول مرة أخرى.")).toBeInTheDocument();
  });

  it("asks for confirmation before deleting, and surfaces a real error on failure", async () => {
    const onDelete = vi.fn().mockRejectedValue(new Error("network error"));
    render(<HoldingRow holding={holding()} onUpdate={vi.fn()} onDelete={onDelete} />);

    fireEvent.click(screen.getByText("حذف"));
    expect(onDelete).not.toHaveBeenCalled();

    fireEvent.click(screen.getByText("نعم، احذف"));
    expect(onDelete).toHaveBeenCalledTimes(1);
    expect(await screen.findByText("تعذّر حذف السهم. حاول مرة أخرى.")).toBeInTheDocument();
  });
});
