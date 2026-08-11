import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import TodayPage from "./page";

/** CONT Phase 6: /today must always disclose freshness/provenance, and
 * must never call anything other than the pure-DB-read personal-
 * opportunities endpoint (no scan-triggering call exists on this page
 * at all -- see fetchTodayData's own comment in page.tsx). */

vi.mock("@/lib/api/market", () => ({
  getPersonalTopOpportunities: vi.fn(),
}));

import { getPersonalTopOpportunities } from "@/lib/api/market";

function opportunity(symbol: string) {
  return {
    rank: 1,
    symbol,
    company_name_ar: null,
    company_name_en: `Company ${symbol}`,
    sector_ar: null,
    decision: "BUY_CANDIDATE",
    decision_label_ar: "شراء",
    simple_decision_ar: "شراء",
    current_price: 30.0,
    market_status: "OPEN",
    market_status_label_ar: "السوق مفتوح",
    entry_zone_low: 29.5,
    entry_zone_high: 30.2,
    entry_status_label_ar: "مناسب الآن",
    is_entry_late: false,
    target_1: 32.0,
    target_2: null,
    target_3: null,
    stop_loss: 29.0,
    risk_reward_target_1: 2.0,
    confidence_score: 80,
    risk_level_label_ar: "متوسطة",
    decision_summary_ar: null,
    entry_confirmation_conditions_ar: [],
    invalidation_conditions: [],
    expected_holding_period_label_ar: null,
    trend_direction_ar: null,
    trend_strength_label_ar: null,
    liquidity_quality_ar: null,
    nearest_resistance: null,
    breakout_level: null,
    decision_timestamp: "2026-08-11T10:00:00Z",
  };
}

describe("TodayPage", () => {
  beforeEach(() => {
    vi.mocked(getPersonalTopOpportunities).mockReset();
  });

  it("shows the fresh-state banner and the opportunity cards when a fresh scan qualifies", async () => {
    vi.mocked(getPersonalTopOpportunities).mockResolvedValue({
      scan_run_id: 1,
      generated_at: "2026-08-11T10:00:00Z",
      data_age_hours: 1,
      max_data_age_hours: 24,
      is_stale: false,
      freshness_state: "FRESH",
      freshness_label_ar: "بيانات حديثة",
      opportunities: [opportunity("2222")],
      message_ar: null,
    });

    render(<TodayPage />);

    expect(await screen.findByText("بيانات حديثة")).toBeInTheDocument();
    expect(screen.getByText("2222")).toBeInTheDocument();
  });

  it("shows the stale-state banner and the honest empty state, never a fabricated opportunity", async () => {
    vi.mocked(getPersonalTopOpportunities).mockResolvedValue({
      scan_run_id: 1,
      generated_at: "2026-08-10T00:00:00Z",
      data_age_hours: 35,
      max_data_age_hours: 24,
      is_stale: true,
      freshness_state: "STALE",
      freshness_label_ar: "بيانات قديمة جدًا لإصدار توصية جديدة",
      opportunities: [],
      message_ar: "البيانات الحالية غير كافية لإصدار توصية جديدة",
    });

    render(<TodayPage />);

    expect(await screen.findByText("بيانات قديمة جدًا لإصدار توصية جديدة")).toBeInTheDocument();
    expect(screen.getByText("البيانات الحالية غير كافية لإصدار توصية جديدة")).toBeInTheDocument();
    expect(screen.queryByText("2222")).not.toBeInTheDocument();
  });

  it("shows the no-scan-yet empty state distinctly from the stale state", async () => {
    vi.mocked(getPersonalTopOpportunities).mockResolvedValue({
      scan_run_id: null,
      generated_at: null,
      data_age_hours: null,
      max_data_age_hours: 24,
      is_stale: true,
      freshness_state: "NO_SCAN",
      freshness_label_ar: "لا يوجد مسح سابق للسوق",
      opportunities: [],
      message_ar: "البيانات الحالية غير كافية لإصدار توصية جديدة",
    });

    render(<TodayPage />);

    expect(await screen.findByText("لا يوجد مسح سابق للسوق")).toBeInTheDocument();
    expect(screen.getByText("لم يُنفَّذ أي مسح للسوق بعد.")).toBeInTheDocument();
  });

  it("re-reads the same pure-read endpoint on button press, never a scan-triggering call", async () => {
    vi.mocked(getPersonalTopOpportunities).mockResolvedValue({
      scan_run_id: 1,
      generated_at: "2026-08-11T10:00:00Z",
      data_age_hours: 1,
      max_data_age_hours: 24,
      is_stale: false,
      freshness_state: "FRESH",
      freshness_label_ar: "بيانات حديثة",
      opportunities: [],
      message_ar: "لا توجد فرصة عالية الجودة حالياً",
    });

    render(<TodayPage />);
    await screen.findByText("بيانات حديثة");

    fireEvent.click(screen.getByRole("button", { name: "امسح السوق الآن" }));

    expect(await screen.findByText("بيانات حديثة")).toBeInTheDocument();
    expect(getPersonalTopOpportunities).toHaveBeenCalledTimes(2);
  });
});
