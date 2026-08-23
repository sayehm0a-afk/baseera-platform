import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import RadarPage from "./page";
import type { RadarHomeSummary } from "@/lib/api/radar-types";

/** GET /api/v1/radar/summary is a read-only, zero-SAHMK-cost view over
 * already-persisted RadarOpportunity rows -- this page never triggers
 * a market scan, only re-reads the same endpoint on button press. */

vi.mock("@/lib/api/radar", () => ({
  getRadarSummary: vi.fn(),
}));

import { getRadarSummary } from "@/lib/api/radar";

function opportunity(
  symbol: string,
  overrides: {
    entry_status?: string;
    entry_status_label_ar?: string;
    id?: number;
    is_decision_fresh?: boolean;
    decision_freshness_status?: "LIVE" | "LAST_SESSION" | "STALE" | "UNKNOWN";
  } = {}
) {
  return {
    id: overrides.id ?? 1,
    symbol,
    company_name_ar: null,
    company_name_en: `Company ${symbol}`,
    classification: "BUY_CANDIDATE" as const,
    classification_label_ar: "شراء",
    confidence_score: 80,
    confidence_disclaimer_ar: "درجة الثقة تقيس قوة واتساق الأدلة المتاحة، وليست احتمال ربح مضمون.",
    basirah_score: 84.0,
    price_at_signal: 30.0,
    entry_zone_low: 29.5,
    entry_zone_high: 30.2,
    stop_loss: 29.0,
    target_1: 32.0,
    target_2: null,
    target_3: null,
    expected_return_target_1: 6.7,
    risk_reward_target_1: 2.0,
    risk_level: "MEDIUM",
    risk_level_label_ar: "متوسطة",
    data_freshness_status: "LIVE" as const,
    entry_status: overrides.entry_status ?? "READY_NOW",
    entry_status_label_ar: overrides.entry_status_label_ar ?? "مناسب الآن",
    stage1_rank: 1,
    stage1_ranking_score: 88.0,
    ranking_reason_ar: "زخم شرائي قوي",
    emitted_at: "2026-08-17T09:00:00Z",
    decision_freshness_status: overrides.decision_freshness_status ?? ("LIVE" as const),
    is_decision_fresh: overrides.is_decision_fresh ?? true,
    decision_v2_snapshot_id: 100,
  };
}

function summary(overrides: Partial<RadarHomeSummary> = {}): RadarHomeSummary {
  return {
    generated_at: "2026-08-17T09:00:00Z",
    live_opportunity_count: 0,
    live_by_classification: {},
    average_confidence: null,
    most_recent_emitted_at: null,
    market_status: "OPEN",
    market_status_label_ar: "السوق مفتوح",
    market_risk_state: "NEUTRAL",
    market_risk_label_ar: "محايد",
    market_risk_basis_ar: "نسبة الإشارات الإيجابية 50% من أصل 20 سهمًا تم فحصها.",
    entry_permitted: true,
    market_risk_is_live: true,
    top_opportunities: [],
    stage1_universe_size: null,
    stage1_evaluated_count: null,
    stage1_candidate_count: null,
    stage2_candidate_cap: 20,
    stage2_validated_count: null,
    final_opportunities_count: null,
    last_full_scan_at: null,
    ...overrides,
  };
}

describe("RadarPage", () => {
  beforeEach(() => {
    vi.mocked(getRadarSummary).mockReset();
  });

  it("shows the honest empty state when the radar has no live opportunities, never a fabricated one", async () => {
    vi.mocked(getRadarSummary).mockResolvedValue(summary());

    render(<RadarPage />);

    expect(await screen.findByText("لا توجد فرص مرصودة حاليًا")).toBeInTheDocument();
    expect(screen.getByText("محايد")).toBeInTheDocument();
  });

  it("shows real live opportunities and the market risk basis text verbatim from the backend", async () => {
    vi.mocked(getRadarSummary).mockResolvedValue(
      summary({
        live_opportunity_count: 1,
        live_by_classification: { BUY_CANDIDATE: 1 },
        average_confidence: 80,
        top_opportunities: [opportunity("2222")],
      })
    );

    render(<RadarPage />);

    expect(await screen.findByText("2222")).toBeInTheDocument();
    expect(screen.getByText("الفرص الحية (1)")).toBeInTheDocument();
    expect(
      screen.getByText("نسبة الإشارات الإيجابية 50% من أصل 20 سهمًا تم فحصها.")
    ).toBeInTheDocument();
  });

  it("shows an entry-blocked market risk state distinctly (red, not green)", async () => {
    vi.mocked(getRadarSummary).mockResolvedValue(
      summary({ market_risk_label_ar: "خروج دفاعي", entry_permitted: false })
    );

    render(<RadarPage />);

    const label = await screen.findByText("خروج دفاعي");
    expect(label.className).toContain("text-bsr-market-down");
  });

  it("shows an error state and lets the user retry", async () => {
    vi.mocked(getRadarSummary).mockRejectedValueOnce(new Error("network error"));

    render(<RadarPage />);

    expect(await screen.findByText("تعذّر تحميل الرادار الذكي")).toBeInTheDocument();

    vi.mocked(getRadarSummary).mockResolvedValueOnce(summary());
    fireEvent.click(screen.getByRole("button", { name: "إعادة المحاولة" }));

    expect(await screen.findByText("لا توجد فرص مرصودة حاليًا")).toBeInTheDocument();
  });

  it("never counts a missed-entry opportunity toward the current/live count, and moves it to a separate section instead of hiding it", async () => {
    vi.mocked(getRadarSummary).mockResolvedValue(
      summary({
        live_opportunity_count: 2,
        live_by_classification: { BUY_CANDIDATE: 2 },
        average_confidence: 80,
        top_opportunities: [
          opportunity("2222", { id: 1 }),
          opportunity("1120", {
            id: 2,
            entry_status: "MISSED_ENTRY",
            entry_status_label_ar: "فاتت نقطة الدخول",
          }),
        ],
      })
    );

    render(<RadarPage />);

    // Only the one still-actionable opportunity counts toward "current live".
    expect(await screen.findByText("الفرص الحية (1)")).toBeInTheDocument();
    // The missed-entry one is not deleted -- it appears in its own section.
    expect(screen.getByText("فرص فاتت نقطة الدخول (1)")).toBeInTheDocument();
    expect(screen.getByText("2222")).toBeInTheDocument();
    expect(screen.getByText("1120")).toBeInTheDocument();
  });

  it("never shows a stale-decision opportunity as a current live BUY, even with entry_status READY_NOW -- moves it to its own labeled section (production regression: symbol 6060)", async () => {
    vi.mocked(getRadarSummary).mockResolvedValue(
      summary({
        live_opportunity_count: 2,
        live_by_classification: { BUY_CANDIDATE: 2 },
        average_confidence: 80,
        top_opportunities: [
          opportunity("2222", { id: 1 }),
          opportunity("6060", {
            id: 2,
            entry_status: "READY_NOW",
            is_decision_fresh: false,
            decision_freshness_status: "STALE",
          }),
        ],
      })
    );

    render(<RadarPage />);

    // Only the fresh decision counts as "الفرص الحية".
    expect(await screen.findByText("الفرص الحية (1)")).toBeInTheDocument();
    // The stale one is not deleted or silently shown as current -- it
    // gets its own clearly-labeled section.
    expect(screen.getByText("تحليل قديم — يحتاج إعادة تقييم (1)")).toBeInTheDocument();
    expect(screen.getByText("2222")).toBeInTheDocument();
    expect(screen.getByText("6060")).toBeInTheDocument();
  });

  it("re-reads the same read-only endpoint on button press", async () => {
    vi.mocked(getRadarSummary).mockResolvedValue(summary());

    render(<RadarPage />);
    await screen.findByText("لا توجد فرص مرصودة حاليًا");

    fireEvent.click(screen.getByRole("button", { name: "تحديث الرادار" }));

    expect(await screen.findByText("لا توجد فرص مرصودة حاليًا")).toBeInTheDocument();
    expect(getRadarSummary).toHaveBeenCalledTimes(2);
  });
});
