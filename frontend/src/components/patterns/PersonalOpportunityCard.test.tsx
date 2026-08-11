import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PersonalOpportunityCard } from "./PersonalOpportunityCard";
import type { PersonalOpportunity } from "@/lib/api/types";

/** GET /api/v1/market/personal/top-opportunities ("امسح السوق الآن")
 * card -- every field here already exists on the backend response, so
 * these tests check rendering fidelity, not scoring/ranking logic. */

const BASE: PersonalOpportunity = {
  rank: 1,
  symbol: "2222",
  company_name_ar: "أرامكو السعودية",
  company_name_en: "Saudi Aramco",
  sector_ar: "الطاقة",
  decision: "BUY_CANDIDATE",
  decision_label_ar: "شراء",
  simple_decision_ar: "شراء",
  current_price: 30.5,
  market_status: "OPEN",
  market_status_label_ar: "السوق مفتوح",
  entry_zone_low: 30.0,
  entry_zone_high: 30.8,
  entry_status_label_ar: "مناسب الآن",
  is_entry_late: false,
  target_1: 32.0,
  target_2: 33.5,
  target_3: null,
  stop_loss: 29.0,
  risk_reward_target_1: 2.4,
  confidence_score: 84,
  risk_level_label_ar: "متوسطة",
  decision_summary_ar: "اختراق مقاومة مع ارتفاع حجم التداول.",
  entry_confirmation_conditions_ar: ["إغلاق فوق المقاومة", "حجم تداول أعلى من المتوسط"],
  invalidation_conditions: ["العودة أسفل مستوى الاختراق"],
  expected_holding_period_label_ar: "خلال جلسة اليوم",
  trend_direction_ar: "صاعد",
  trend_strength_label_ar: "قوي",
  liquidity_quality_ar: "جيدة",
  nearest_resistance: 31.5,
  breakout_level: 30.8,
  decision_timestamp: "2026-08-11T10:00:00Z",
};

describe("PersonalOpportunityCard", () => {
  it("renders the rank, company name, symbol, and simple Arabic decision", () => {
    render(<PersonalOpportunityCard opportunity={BASE} />);
    expect(screen.getByText("#1")).toBeInTheDocument();
    expect(screen.getByText("أرامكو السعودية")).toBeInTheDocument();
    expect(screen.getByText(/2222/)).toBeInTheDocument();
    expect(screen.getByText("قرار بصيرة: شراء")).toBeInTheDocument();
  });

  it("renders entry zone, targets, and stop loss", () => {
    render(<PersonalOpportunityCard opportunity={BASE} />);
    expect(screen.getByText("30.00 – 30.80")).toBeInTheDocument();
    expect(screen.getByText("32.00")).toBeInTheDocument();
    expect(screen.getByText("33.50")).toBeInTheDocument();
    expect(screen.getByText("29.00")).toBeInTheDocument();
  });

  it("renders a placeholder for a missing target rather than blank/undefined", () => {
    render(<PersonalOpportunityCard opportunity={BASE} />);
    expect(screen.getAllByText("--").length).toBeGreaterThan(0);
  });

  it("flags a late entry with the market-down color, not the normal secondary text", () => {
    render(<PersonalOpportunityCard opportunity={{ ...BASE, is_entry_late: true, entry_status_label_ar: "فاتت نقطة الدخول" }} />);
    const status = screen.getByText("فاتت نقطة الدخول");
    expect(status.className).toContain("bsr-market-down");
  });

  it("renders the reasoning, confirmation signals, and the top invalidation reason", () => {
    render(<PersonalOpportunityCard opportunity={BASE} />);
    expect(screen.getByText("اختراق مقاومة مع ارتفاع حجم التداول.")).toBeInTheDocument();
    expect(screen.getByText("إغلاق فوق المقاومة")).toBeInTheDocument();
    expect(screen.getByText("العودة أسفل مستوى الاختراق")).toBeInTheDocument();
  });

  it("links to the stock detail page for the same symbol", () => {
    render(<PersonalOpportunityCard opportunity={BASE} />);
    expect(screen.getByRole("link", { name: "التفاصيل" })).toHaveAttribute("href", "/stocks/2222");
  });

  it("renders the Arabic market-status label, never the raw English enum value", () => {
    render(<PersonalOpportunityCard opportunity={BASE} />);
    expect(screen.getByText("السوق مفتوح")).toBeInTheDocument();
    expect(screen.queryByText("OPEN")).not.toBeInTheDocument();
  });
});
