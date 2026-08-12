import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { StockDetailClient } from "./StockDetailClient";

/** Regression: the M7 production UX audit found that when the market
 * data provider is unavailable (e.g. SAHMK daily quota exhausted),
 * the executive decision panel silently rendered nothing at all, and
 * the legacy overview panel showed "insufficient historical data" --
 * a misleading message, since the real cause was a live-data outage,
 * not a lack of history. Both panels now render an honest, distinct
 * "provider unavailable" message instead. */

vi.mock("@/lib/api/stocks", () => ({
  getStock: vi.fn(),
  getQuote: vi.fn(),
  getHistory: vi.fn(),
  getTechnicalAnalysis: vi.fn(),
  getDecision: vi.fn(),
  getDecisionV2: vi.fn(),
  getFundamentalAnalysis: vi.fn(),
  getAnalystReport: vi.fn(),
}));

import { ApiError } from "@/lib/api/client";
import {
  getAnalystReport,
  getDecision,
  getDecisionV2,
  getFundamentalAnalysis,
  getHistory,
  getQuote,
  getStock,
  getTechnicalAnalysis,
} from "@/lib/api/stocks";

function providerUnavailable() {
  return Promise.reject(new ApiError(503, "provider_unavailable", "provider down"));
}

describe("StockDetailClient", () => {
  it("shows an honest 'provider unavailable' message on both the executive decision panel and the legacy overview panel, instead of blank content or a misleading 'insufficient data' message", async () => {
    vi.mocked(getStock).mockResolvedValue({
      symbol: "6004",
      name_en: "Catrion",
      name_ar: "كاتريون",
      sector: "Commercial & Professional Svc",
      sector_ar: "الخدمات التجارية والمهنية",
      currency: "SAR",
      is_active: true,
    });
    vi.mocked(getQuote).mockImplementation(providerUnavailable);
    vi.mocked(getDecisionV2).mockImplementation(providerUnavailable);
    vi.mocked(getDecision).mockImplementation(providerUnavailable);
    vi.mocked(getHistory).mockImplementation(providerUnavailable);
    vi.mocked(getTechnicalAnalysis).mockImplementation(providerUnavailable);
    vi.mocked(getFundamentalAnalysis).mockImplementation(providerUnavailable);
    vi.mocked(getAnalystReport).mockImplementation(providerUnavailable);

    render(<StockDetailClient symbol="6004" />);

    expect(await screen.findByText("تعذّر تحميل قرار الذكاء الاصطناعي")).toBeInTheDocument();
    expect(await screen.findByText("تعذّر تحميل التوصية الآلية")).toBeInTheDocument();

    // The old, misleading "insufficient data" copy must not appear when
    // the real cause is a provider outage.
    expect(screen.queryByText("البيانات غير كافية لإصدار قرار")).not.toBeInTheDocument();
    expect(
      screen.queryByText("غالباً بسبب نقص بيانات تاريخية كافية لتشغيل محرك القرار.")
    ).not.toBeInTheDocument();

    // Both messages explain the real cause: the market data provider,
    // not the stock's own history, is unavailable.
    expect(screen.getAllByText(/مزود بيانات السوق غير متاح حالياً/).length).toBeGreaterThanOrEqual(2);
  });

  it("still shows the real 'insufficient data' message when the decision engine genuinely lacks enough data for the symbol", async () => {
    vi.mocked(getStock).mockResolvedValue({
      symbol: "9999",
      name_en: "New Listing",
      name_ar: "إدراج جديد",
      sector: null,
      sector_ar: null,
      currency: "SAR",
      is_active: true,
    });
    vi.mocked(getQuote).mockImplementation(providerUnavailable);
    vi.mocked(getDecisionV2).mockRejectedValue(new ApiError(422, "insufficient_data", "not enough data"));
    vi.mocked(getDecision).mockRejectedValue(new ApiError(422, "insufficient_data", "not enough data"));
    vi.mocked(getHistory).mockImplementation(providerUnavailable);
    vi.mocked(getTechnicalAnalysis).mockImplementation(providerUnavailable);
    vi.mocked(getFundamentalAnalysis).mockImplementation(providerUnavailable);
    vi.mocked(getAnalystReport).mockImplementation(providerUnavailable);

    render(<StockDetailClient symbol="9999" />);

    expect(await screen.findByText("البيانات غير كافية لإصدار قرار")).toBeInTheDocument();
    expect(
      await screen.findByText("غالباً بسبب نقص بيانات تاريخية كافية لتشغيل محرك القرار.")
    ).toBeInTheDocument();
  });
});
