import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { FollowedSignalsPanel } from "./FollowedSignalsPanel";
import type { FollowedSignal } from "@/lib/api/signals-types";

vi.mock("@/lib/api/signals", () => ({
  getFollowedSignals: vi.fn(),
}));

import { getFollowedSignals } from "@/lib/api/signals";

function buildSignal(overrides: Partial<FollowedSignal> = {}): FollowedSignal {
  return {
    id: 1,
    decision_v2_snapshot_id: 100,
    symbol: "2222",
    company_name_ar: "أرامكو السعودية",
    followed_at: "2026-09-18T09:00:00Z",
    decision: "BUY_CANDIDATE",
    decision_label_ar: "شراء",
    entry_zone_low: 30.0,
    entry_zone_high: 30.6,
    stop_loss: 29.0,
    target_1: 32.0,
    target_2: null,
    target_3: null,
    outcome_status: null,
    outcome_status_label_ar: null,
    outcome_return_pct: null,
    ...overrides,
  };
}

describe("FollowedSignalsPanel", () => {
  it("shows an empty state when the user follows nothing yet", async () => {
    vi.mocked(getFollowedSignals).mockResolvedValue({ generated_at: "2026-09-18T09:00:00Z", items: [] });

    render(<FollowedSignalsPanel />);

    expect(await screen.findByText("لا تتابع أي إشارة بعد")).toBeInTheDocument();
  });

  it("renders a followed signal still pending, never fabricating an outcome", async () => {
    vi.mocked(getFollowedSignals).mockResolvedValue({
      generated_at: "2026-09-18T09:00:00Z",
      items: [buildSignal()],
    });

    render(<FollowedSignalsPanel />);

    expect(await screen.findByText("2222")).toBeInTheDocument();
    expect(screen.getByText("قيد المتابعة")).toBeInTheDocument();
  });

  it("shows the real outcome and realized return once one exists", async () => {
    vi.mocked(getFollowedSignals).mockResolvedValue({
      generated_at: "2026-09-18T09:00:00Z",
      items: [
        buildSignal({
          outcome_status: "TARGET_1_HIT",
          outcome_status_label_ar: "تحقق الهدف الأول",
          outcome_return_pct: 4.92,
        }),
      ],
    });

    render(<FollowedSignalsPanel />);

    expect(await screen.findByText("تحقق الهدف الأول")).toBeInTheDocument();
    expect(screen.getByText(/العائد المحقق: \+4\.92%/)).toBeInTheDocument();
  });

  it("shows an error state on a genuine load failure", async () => {
    vi.mocked(getFollowedSignals).mockRejectedValue(new Error("boom"));

    render(<FollowedSignalsPanel />);

    expect(await screen.findByText("تعذّر تحميل الإشارات المتابَعة")).toBeInTheDocument();
  });
});
