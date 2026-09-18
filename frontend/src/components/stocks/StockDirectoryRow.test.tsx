import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StockDirectoryRow } from "./StockDirectoryRow";
import type { StockDirectoryItem } from "@/lib/api/stocks-types";

function buildItem(overrides: Partial<StockDirectoryItem> = {}): StockDirectoryItem {
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
    latest_decision: null,
    latest_decision_label_ar: null,
    latest_confidence_score: null,
    latest_target_1: null,
    market: "TADAWUL",
    currency: "SAR",
    ...overrides,
  };
}

describe("StockDirectoryRow", () => {
  it("omits the classification hint entirely when this symbol has never been analyzed", () => {
    render(<StockDirectoryRow item={buildItem()} />);
    expect(screen.queryByText(/هدف/)).not.toBeInTheDocument();
  });

  it("shows the real latest classification and target for an actionable BUY decision", () => {
    render(
      <StockDirectoryRow
        item={buildItem({
          latest_decision: "STRONG_BUY_CANDIDATE",
          latest_decision_label_ar: "شراء قوي",
          latest_confidence_score: 82.5,
          latest_target_1: 34.0,
        })}
      />
    );

    expect(screen.getByText("شراء قوي")).toBeInTheDocument();
    expect(screen.getByText("هدف 34.00")).toBeInTheDocument();
  });

  it("shows the classification but never a target for a non-actionable decision, even if one is present in the data", () => {
    render(
      <StockDirectoryRow
        item={buildItem({
          latest_decision: "WATCH",
          latest_decision_label_ar: "مراقبة",
          latest_confidence_score: 40,
          latest_target_1: 34.0,
        })}
      />
    );

    expect(screen.getByText("مراقبة")).toBeInTheDocument();
    expect(screen.queryByText(/هدف/)).not.toBeInTheDocument();
  });

  it("shows no currency badge for a Tadawul (default-market) row", () => {
    render(<StockDirectoryRow item={buildItem()} />);
    expect(screen.queryByText("SAR")).not.toBeInTheDocument();
  });

  it("shows a currency badge for a US-market row", () => {
    render(
      <StockDirectoryRow
        item={buildItem({ symbol: "AAPL", name_en: "Apple Inc.", market: "US", currency: "USD" })}
      />
    );
    expect(screen.getByText("USD")).toBeInTheDocument();
    expect(screen.getByText("AAPL")).toBeInTheDocument();
  });
});
