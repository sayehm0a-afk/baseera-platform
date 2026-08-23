import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import PortfolioPage from "./page";
import type { PortfolioHoldingDetail, PortfolioHoldings, PortfolioSummary } from "@/lib/api/portfolio-types";

/** RADAR-C Phase H: the Smart Portfolio page is DB-only on load (GET
 * /api/v1/portfolio + GET /api/v1/portfolio/{id}/holdings) -- it never
 * triggers a live SAHMK call unless the user explicitly opts into the
 * "تحليل شامل" (full analysis) button. */

vi.mock("@/lib/api/portfolio", () => ({
  listMyPortfolios: vi.fn(),
  createPortfolio: vi.fn(),
  deletePortfolio: vi.fn(),
  getPortfolioHoldings: vi.fn(),
  addPortfolioHolding: vi.fn(),
  updatePortfolioHolding: vi.fn(),
  deletePortfolioHolding: vi.fn(),
  analyzePortfolio: vi.fn(),
}));

vi.mock("@/lib/api/stocks", () => ({
  searchStocks: vi.fn().mockResolvedValue({ query: "", results: [] }),
}));

import {
  addPortfolioHolding,
  createPortfolio,
  deletePortfolioHolding,
  getPortfolioHoldings,
  listMyPortfolios,
  updatePortfolioHolding,
} from "@/lib/api/portfolio";

function summary(overrides: Partial<PortfolioSummary> = {}): PortfolioSummary {
  return {
    id: 1,
    name: "محفظتي",
    cash_balance: 500,
    holdings_count: 1,
    created_at: "2026-08-01T00:00:00Z",
    updated_at: "2026-08-01T00:00:00Z",
    ...overrides,
  };
}

function holding(overrides: Partial<PortfolioHoldingDetail> = {}): PortfolioHoldingDetail {
  return {
    id: 10,
    symbol: "2222",
    name_ar: "أرامكو السعودية",
    name_en: "Saudi Aramco",
    sector: "Energy",
    sector_ar: "الطاقة",
    quantity: 100,
    average_cost: 30,
    current_price: 33,
    price_as_of: "2026-08-17T00:00:00Z",
    freshness_label_ar: "آخر جلسة",
    invested_cost: 3000,
    current_value: 3300,
    unrealized_pnl: 300,
    unrealized_pnl_pct: 10,
    guidance_decision: "HOLD",
    guidance_label_ar: "احتفاظ",
    guidance_basis_ar: "الأدلة الحالية تدعم الاستمرار في الاحتفاظ بالسهم.",
    guidance_confidence: 70,
    guidance_evaluated_at: "2026-08-17T00:00:00Z",
    guidance_freshness_status: "LIVE" as const,
    is_guidance_fresh: true,
    ...overrides,
  };
}

function holdings(overrides: Partial<PortfolioHoldings> = {}): PortfolioHoldings {
  return {
    portfolio_id: 1,
    name: "محفظتي",
    cash_balance: 500,
    holdings: [holding()],
    total_invested_cost: 3000,
    total_current_value: 3300,
    total_unrealized_pnl: 300,
    total_unrealized_pnl_pct: 10,
    total_value_with_cash: 3800,
    ...overrides,
  };
}

describe("PortfolioPage", () => {
  beforeEach(() => {
    vi.mocked(listMyPortfolios).mockReset();
    vi.mocked(createPortfolio).mockReset();
    vi.mocked(getPortfolioHoldings).mockReset();
    vi.mocked(addPortfolioHolding).mockReset();
    vi.mocked(updatePortfolioHolding).mockReset();
    vi.mocked(deletePortfolioHolding).mockReset();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("uses the caller's existing portfolio when one already exists, never creating a new one", async () => {
    vi.mocked(listMyPortfolios).mockResolvedValue({ portfolios: [summary()] });
    vi.mocked(getPortfolioHoldings).mockResolvedValue(holdings());

    render(<PortfolioPage />);

    expect(await screen.findByText("أرامكو السعودية")).toBeInTheDocument();
    expect(createPortfolio).not.toHaveBeenCalled();
    expect(getPortfolioHoldings).toHaveBeenCalledWith(1);
  });

  it("creates a portfolio only when the caller genuinely has none yet", async () => {
    vi.mocked(listMyPortfolios).mockResolvedValue({ portfolios: [] });
    vi.mocked(createPortfolio).mockResolvedValue(summary({ id: 7, holdings_count: 0 }));
    vi.mocked(getPortfolioHoldings).mockResolvedValue(holdings({ portfolio_id: 7, holdings: [], total_invested_cost: 0, total_current_value: 0, total_unrealized_pnl: null, total_unrealized_pnl_pct: null, total_value_with_cash: 500 }));

    render(<PortfolioPage />);

    expect(await screen.findByText("لم تتم إضافة أي سهم بعد")).toBeInTheDocument();
    expect(createPortfolio).toHaveBeenCalledWith({ name: "محفظتي" });
    expect(getPortfolioHoldings).toHaveBeenCalledWith(7);
  });

  it("shows an honest error state when loading the portfolio fails, not a silent blank page", async () => {
    vi.mocked(listMyPortfolios).mockRejectedValue(new Error("network error"));

    render(<PortfolioPage />);

    expect(await screen.findByText("تعذّر تحميل محفظتك")).toBeInTheDocument();
  });

  it("renders real totals from the backend, never a client-computed figure", async () => {
    vi.mocked(listMyPortfolios).mockResolvedValue({ portfolios: [summary()] });
    vi.mocked(getPortfolioHoldings).mockResolvedValue(holdings());

    render(<PortfolioPage />);

    await screen.findByText("أرامكو السعودية");
    expect(screen.getByText("3000.00")).toBeInTheDocument();
    // "3300.00" appears both as the portfolio-level total and as this
    // single holding's own current value -- both are real, so both
    // are expected, not a bug to work around.
    expect(screen.getAllByText("3300.00").length).toBe(2);
    expect(screen.getByText("3800.00")).toBeInTheDocument();
  });

  it("shows the holder guidance badge from the backend, distinct from a fresh buy recommendation", async () => {
    vi.mocked(listMyPortfolios).mockResolvedValue({ portfolios: [summary()] });
    vi.mocked(getPortfolioHoldings).mockResolvedValue(holdings());

    render(<PortfolioPage />);

    expect(await screen.findByText("احتفاظ")).toBeInTheDocument();
  });

  it("shows an honest 'no guidance yet' pill instead of fabricating one when no Decision V2 snapshot exists", async () => {
    vi.mocked(listMyPortfolios).mockResolvedValue({ portfolios: [summary()] });
    vi.mocked(getPortfolioHoldings).mockResolvedValue(
      holdings({ holdings: [holding({ guidance_decision: null, guidance_label_ar: null })] })
    );

    render(<PortfolioPage />);

    expect(await screen.findByText("بلا توصية بعد")).toBeInTheDocument();
  });

  it("adds a new holding and reloads the real holdings list afterward", async () => {
    vi.mocked(listMyPortfolios).mockResolvedValue({ portfolios: [summary({ holdings_count: 0 })] });
    vi.mocked(getPortfolioHoldings)
      .mockResolvedValueOnce(holdings({ holdings: [], total_invested_cost: 0, total_current_value: 0, total_unrealized_pnl: null, total_unrealized_pnl_pct: null, total_value_with_cash: 500 }))
      .mockResolvedValueOnce(holdings());
    vi.mocked(addPortfolioHolding).mockResolvedValue(holding());

    render(<PortfolioPage />);
    await screen.findByText("لم تتم إضافة أي سهم بعد");

    fireEvent.change(screen.getByPlaceholderText("رمز السهم أو اسم الشركة"), { target: { value: "2222" } });
    fireEvent.change(screen.getByPlaceholderText("الكمية"), { target: { value: "100" } });
    fireEvent.change(screen.getByPlaceholderText("متوسط سعر الشراء"), { target: { value: "30" } });
    await act(async () => {
      fireEvent.click(screen.getByText("إضافة"));
    });

    await waitFor(() => {
      expect(addPortfolioHolding).toHaveBeenCalledWith(1, { symbol: "2222", quantity: 100, average_cost: 30 });
    });
    expect(await screen.findByText("أرامكو السعودية")).toBeInTheDocument();
  });

  it("edits a holding's quantity and average cost, then reloads real totals", async () => {
    vi.mocked(listMyPortfolios).mockResolvedValue({ portfolios: [summary()] });
    vi.mocked(getPortfolioHoldings)
      .mockResolvedValueOnce(holdings())
      .mockResolvedValueOnce(
        holdings({ holdings: [holding({ quantity: 150, average_cost: 32, invested_cost: 4800 })] })
      );
    vi.mocked(updatePortfolioHolding).mockResolvedValue(holding({ quantity: 150, average_cost: 32 }));

    render(<PortfolioPage />);
    await screen.findByText("أرامكو السعودية");

    fireEvent.click(screen.getByText("تعديل"));
    const quantityInput = screen.getByDisplayValue("100");
    fireEvent.change(quantityInput, { target: { value: "150" } });
    const costInput = screen.getByDisplayValue("30");
    fireEvent.change(costInput, { target: { value: "32" } });
    await act(async () => {
      fireEvent.click(screen.getByText("حفظ"));
    });

    await waitFor(() => {
      expect(updatePortfolioHolding).toHaveBeenCalledWith(1, 10, { quantity: 150, average_cost: 32 });
    });
  });

  it("deletes a holding only after inline confirmation", async () => {
    vi.mocked(listMyPortfolios).mockResolvedValue({ portfolios: [summary()] });
    vi.mocked(getPortfolioHoldings)
      .mockResolvedValueOnce(holdings())
      .mockResolvedValueOnce(
        holdings({ holdings: [], total_invested_cost: 0, total_current_value: 0, total_unrealized_pnl: null, total_unrealized_pnl_pct: null, total_value_with_cash: 500 })
      );
    vi.mocked(deletePortfolioHolding).mockResolvedValue({ message: "تمت الإزالة" });

    render(<PortfolioPage />);
    await screen.findByText("أرامكو السعودية");

    fireEvent.click(screen.getByText("حذف"));
    expect(deletePortfolioHolding).not.toHaveBeenCalled();

    await act(async () => {
      fireEvent.click(screen.getByText("نعم، احذف"));
    });

    await waitFor(() => {
      expect(deletePortfolioHolding).toHaveBeenCalledWith(1, 10);
    });
    expect(await screen.findByText("لم تتم إضافة أي سهم بعد")).toBeInTheDocument();
  });

  it("keeps the full multi-engine analysis collapsed behind an explicit opt-in button", async () => {
    vi.mocked(listMyPortfolios).mockResolvedValue({ portfolios: [summary()] });
    vi.mocked(getPortfolioHoldings).mockResolvedValue(holdings());

    render(<PortfolioPage />);
    await screen.findByText("أرامكو السعودية");

    expect(screen.queryByText("تشغيل التحليل الشامل")).not.toBeInTheDocument();
    fireEvent.click(screen.getByText("التحليل الشامل للمحفظة"));
    expect(await screen.findByText("تشغيل التحليل الشامل")).toBeInTheDocument();
  });
});
