import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import StrategiesPage from "./page";
import type { BacktestRun } from "@/lib/api/backtests-types";
import type { FullBacktestReport } from "@/lib/api/backtest-metrics-types";

vi.mock("@/lib/api/backtests", () => ({
  createBacktest: vi.fn(),
  getBacktest: vi.fn(),
  getBacktestMetrics: vi.fn(),
}));

import { createBacktest, getBacktest, getBacktestMetrics } from "@/lib/api/backtests";

const baseRun: BacktestRun = {
  id: 1,
  idempotency_key: "key",
  status: "SUCCESS",
  symbols: ["2222"],
  strategy: "ai_decision_engine",
  data_provenance_mode: "LIVE",
  start_date: "2026-01-01",
  end_date: "2026-06-01",
  evaluation_frequency_days: 5,
  holding_horizon_days: 10,
  target_price_horizon_days: 10,
  transaction_cost_bps: 0,
  slippage_bps: 0,
  confidence_threshold: null,
  recommendation_threshold: null,
  fundamental_reporting_lag_days: 0,
  calibration_version: null,
  progress_current: 1,
  progress_total: 1,
  error_message: null,
  started_at: null,
  finished_at: null,
  duration_seconds: 1,
  created_at: "2026-01-01T00:00:00Z",
};

const baseReport: FullBacktestReport = {
  overall: {
    evaluation_count: 10,
    direction_accuracy: 0.6,
    target_price_hit_rate: 0.5,
    stop_loss_hit_rate: 0.1,
    average_forward_return_pct: 1.5,
    median_forward_return_pct: 1.2,
    win_rate: 0.7,
    loss_rate: 0,
    // Zero losing trades -> profit_factor is +Infinity.
    profit_factor: Infinity,
    max_drawdown: 0.05,
    volatility: 0.02,
    downside_deviation: 0.01,
    sharpe_ratio: 1.1,
    sortino_ratio: 1.3,
    calibration_error: null,
  },
  evaluated_count: 10,
  filtered_count: 10,
  skipped: {},
  cancelled: false,
};

describe("StrategiesPage", () => {
  it("rejects a start date after the end date before calling the backend", async () => {
    render(<StrategiesPage />);

    fireEvent.change(screen.getByLabelText("تاريخ البداية"), { target: { value: "2026-06-01" } });
    fireEvent.change(screen.getByLabelText("تاريخ النهاية"), { target: { value: "2026-01-01" } });
    fireEvent.click(screen.getByRole("button", { name: "اختبار الاستراتيجية" }));

    expect(await screen.findByText("تاريخ البداية يجب أن يسبق تاريخ النهاية.")).toBeInTheDocument();
    expect(createBacktest).not.toHaveBeenCalled();
  });

  it("renders an Infinity profit_factor as the math symbol, not the literal string", async () => {
    vi.mocked(createBacktest).mockResolvedValue(baseRun);
    vi.mocked(getBacktest).mockResolvedValue(baseRun);
    vi.mocked(getBacktestMetrics).mockResolvedValue({
      id: 1,
      status: "SUCCESS",
      data_provenance_mode: "LIVE",
      symbols: ["2222"],
      metrics: baseReport as unknown as Record<string, unknown>,
    });

    render(<StrategiesPage />);
    fireEvent.click(screen.getByRole("button", { name: "اختبار الاستراتيجية" }));

    expect(await screen.findByText("∞")).toBeInTheDocument();
    expect(screen.queryByText("Infinity")).not.toBeInTheDocument();
  });
});
