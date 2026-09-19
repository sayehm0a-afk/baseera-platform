import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { PersonalPerformancePanel } from "./PersonalPerformancePanel";
import type { PersonalPerformanceComparison } from "@/lib/api/signals-types";

vi.mock("@/lib/api/signals", () => ({
  getPersonalPerformance: vi.fn(),
}));

import { getPersonalPerformance } from "@/lib/api/signals";

function buildComparison(overrides: Partial<PersonalPerformanceComparison> = {}): PersonalPerformanceComparison {
  return {
    generated_at: "2026-09-18T09:00:00Z",
    personal_resolved_sample_size: 12,
    personal_win_rate_pct: 66.67,
    personal_small_sample_warning: false,
    algorithm_resolved_sample_size: 200,
    algorithm_win_rate_pct: 58.5,
    algorithm_small_sample_warning: false,
    insufficient_data_message_ar: null,
    ...overrides,
  };
}

describe("PersonalPerformancePanel", () => {
  it("shows an honest insufficient-data state rather than fabricating a comparison", async () => {
    vi.mocked(getPersonalPerformance).mockResolvedValue(
      buildComparison({
        personal_resolved_sample_size: 0,
        personal_win_rate_pct: null,
        algorithm_resolved_sample_size: 0,
        algorithm_win_rate_pct: null,
        insufficient_data_message_ar: "بيانات غير كافية بعد لعرض هذا المقياس بشكل موثوق",
      })
    );

    render(<PersonalPerformancePanel />);

    expect(await screen.findByText("لا توجد بيانات كافية بعد")).toBeInTheDocument();
  });

  it("renders both real win rates side by side", async () => {
    vi.mocked(getPersonalPerformance).mockResolvedValue(buildComparison());

    render(<PersonalPerformancePanel />);

    expect(await screen.findByText("67%")).toBeInTheDocument();
    expect(screen.getByText("59%")).toBeInTheDocument();
    expect(screen.getByText(/من 12 إشارة محسومة تابعتها/)).toBeInTheDocument();
    expect(screen.getByText(/من 200 إشارة محسومة على مستوى المنصة/)).toBeInTheDocument();
  });

  it("shows a small-sample warning without hiding the real number", async () => {
    vi.mocked(getPersonalPerformance).mockResolvedValue(
      buildComparison({ personal_resolved_sample_size: 2, personal_small_sample_warning: true })
    );

    render(<PersonalPerformancePanel />);

    expect(await screen.findByText(/عينة صغيرة/)).toBeInTheDocument();
  });

  it("shows a preliminary-sample warning on the algorithm side, without hiding the real number", async () => {
    // 2026-09-19 (full-platform audit): the algorithm-wide win rate is
    // a platform-level track-record claim -- it must be flagged below
    // the 30-outcome floor this platform enforces everywhere else for
    // that kind of claim, not shown as an unqualified headline number.
    vi.mocked(getPersonalPerformance).mockResolvedValue(
      buildComparison({ algorithm_resolved_sample_size: 2, algorithm_small_sample_warning: true })
    );

    render(<PersonalPerformancePanel />);

    expect(await screen.findByText(/عينة أولية/)).toBeInTheDocument();
    expect(screen.getByText("59%")).toBeInTheDocument(); // the real number is never hidden
  });

  it("shows an error state on a genuine load failure", async () => {
    vi.mocked(getPersonalPerformance).mockRejectedValue(new Error("boom"));

    render(<PersonalPerformancePanel />);

    expect(await screen.findByText("تعذّر تحميل مقارنة الأداء")).toBeInTheDocument();
  });
});
