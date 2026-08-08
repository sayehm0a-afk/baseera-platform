import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { RecommendationHistoryPanel } from "./RecommendationHistoryPanel";
import type {
  RecommendationHistoryItem,
  RecommendationHistoryStats,
} from "@/lib/api/recommendation-history-types";

vi.mock("@/lib/api/recommendation-history", () => ({
  getRecommendationHistory: vi.fn(),
  getRecommendationHistoryStats: vi.fn(),
}));

import { getRecommendationHistory, getRecommendationHistoryStats } from "@/lib/api/recommendation-history";

function buildItem(overrides: Partial<RecommendationHistoryItem> = {}): RecommendationHistoryItem {
  return {
    id: 1,
    symbol: "2222",
    company_name_ar: "أرامكو السعودية",
    sector: "Energy",
    evaluated_at: "2026-08-01T00:00:00Z",
    recommendation: "BUY",
    confidence_score: 72,
    calibrated_confidence_score: null,
    market_price_at_evaluation: 30,
    target_price: 33,
    target_price_2: null,
    target_price_3: null,
    stop_loss: 28,
    expected_return_pct: 10,
    time_horizon: "MEDIUM",
    risk_level: "MODERATE",
    position_size: "STANDARD",
    expires_at: null,
    reasons: ["مؤشرات فنية إيجابية"],
    engine_version: "2.0.0",
    is_paper_trade: false,
    overall_status: "COMPLETED",
    outcomes: [
      {
        evaluation_horizon_days: 7,
        status: "SUCCESSFUL",
        due_at: "2026-08-08T00:00:00Z",
        evaluated_at: "2026-08-08T00:00:00Z",
        price_at_evaluation: 32,
        return_pct: 6.5,
        hit_target: true,
        hit_stop: false,
        target_1_reached: true,
        target_1_reached_at: null,
        target_2_reached: null,
        target_2_reached_at: null,
        target_3_reached: null,
        target_3_reached_at: null,
        max_favorable_excursion_pct: null,
        max_adverse_excursion_pct: null,
        time_to_target_days: 5,
      },
    ],
    ...overrides,
  };
}

function buildStats(overrides: Partial<RecommendationHistoryStats> = {}): RecommendationHistoryStats {
  return {
    generated_at: "2026-08-08T00:00:00Z",
    evaluation_horizon_days: 7,
    sample_size: 3,
    terminal_sample_size: 3,
    win_rate: 66.67,
    average_return_pct: 4.1,
    target_hit_rate: 66.67,
    stop_hit_rate: 33.33,
    status_counts: { SUCCESSFUL: 2, FAILED: 1 },
    small_sample_warning: true,
    ...overrides,
  };
}

describe("RecommendationHistoryPanel", () => {
  it("shows an empty state when there is no history yet", async () => {
    vi.mocked(getRecommendationHistory).mockResolvedValue({
      generated_at: "2026-08-08T00:00:00Z",
      total: 0,
      items: [],
    });
    vi.mocked(getRecommendationHistoryStats).mockResolvedValue(buildStats({ sample_size: 0, terminal_sample_size: 0, win_rate: null }));

    render(<RecommendationHistoryPanel />);

    expect(await screen.findByText("لا يوجد سجل توصيات بعد")).toBeInTheDocument();
  });

  it("renders a real history item with its real outcome, including failures", async () => {
    vi.mocked(getRecommendationHistory).mockResolvedValue({
      generated_at: "2026-08-08T00:00:00Z",
      total: 1,
      items: [
        buildItem({
          outcomes: [
            {
              evaluation_horizon_days: 7,
              status: "FAILED",
              due_at: "2026-08-08T00:00:00Z",
              evaluated_at: "2026-08-08T00:00:00Z",
              price_at_evaluation: 27,
              return_pct: -10,
              hit_target: false,
              hit_stop: true,
              target_1_reached: false,
              target_1_reached_at: null,
              target_2_reached: null,
              target_2_reached_at: null,
              target_3_reached: null,
              target_3_reached_at: null,
              max_favorable_excursion_pct: null,
              max_adverse_excursion_pct: null,
              time_to_target_days: null,
            },
          ],
        }),
      ],
    });
    vi.mocked(getRecommendationHistoryStats).mockResolvedValue(buildStats());

    render(<RecommendationHistoryPanel />);

    expect(await screen.findByText("2222")).toBeInTheDocument();
    expect(screen.getByText(/فاشلة/)).toBeInTheDocument();
    expect(screen.getByText(/-10%/)).toBeInTheDocument();
  });

  it("shows the small-sample warning when the terminal sample is below 30", async () => {
    vi.mocked(getRecommendationHistory).mockResolvedValue({
      generated_at: "2026-08-08T00:00:00Z",
      total: 0,
      items: [],
    });
    vi.mocked(getRecommendationHistoryStats).mockResolvedValue(buildStats());

    render(<RecommendationHistoryPanel />);

    expect(await screen.findByText(/عيّنة صغيرة/)).toBeInTheDocument();
  });

  it("shows an error state when the fetch fails", async () => {
    vi.mocked(getRecommendationHistory).mockRejectedValue(new Error("network error"));
    vi.mocked(getRecommendationHistoryStats).mockResolvedValue(buildStats());

    render(<RecommendationHistoryPanel />);

    await waitFor(() => expect(screen.getByText("تعذّر تحميل سجل التوصيات")).toBeInTheDocument());
  });

  it("passes the symbol through to the history fetch when narrowing to one stock", async () => {
    vi.mocked(getRecommendationHistory).mockResolvedValue({
      generated_at: "2026-08-08T00:00:00Z",
      total: 0,
      items: [],
    });
    vi.mocked(getRecommendationHistoryStats).mockResolvedValue(buildStats());

    render(<RecommendationHistoryPanel symbol="1120" />);

    await waitFor(() =>
      expect(getRecommendationHistory).toHaveBeenCalledWith({ symbol: "1120", limit: 50 })
    );
  });
});
