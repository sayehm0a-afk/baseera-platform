import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { RunScanButton } from "./RunScanButton";

vi.mock("@/lib/api/market", () => ({
  triggerScan: vi.fn(),
  getScanRun: vi.fn(),
}));

import { getScanRun, triggerScan } from "@/lib/api/market";

const baseRun = {
  id: 1,
  status: "PENDING",
  symbols_requested: 10,
  symbols_succeeded: 0,
  symbols_skipped: 0,
  symbols_failed: 0,
  error_summary: null,
  started_at: null,
  finished_at: null,
  duration_seconds: null,
  created_at: "2026-09-19T00:00:00Z",
};

describe("RunScanButton", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.clearAllMocks();
  });

  it("calls onScanComplete once the polled run reaches SUCCESS", async () => {
    vi.useFakeTimers();
    vi.mocked(triggerScan).mockResolvedValue({ ...baseRun, status: "PENDING" });
    vi.mocked(getScanRun).mockResolvedValue({ ...baseRun, status: "SUCCESS" });
    const onScanComplete = vi.fn();

    render(<RunScanButton onScanComplete={onScanComplete} />);
    fireEvent.click(screen.getByRole("button"));

    await vi.runOnlyPendingTimersAsync();
    await Promise.resolve();

    expect(onScanComplete).toHaveBeenCalledTimes(1);
    expect(screen.queryByText(/ما زال قيد التنفيذ/)).not.toBeInTheDocument();
  });

  it("shows a distinct timeout message and does not report success if the scan never finishes", async () => {
    vi.useFakeTimers();
    vi.mocked(triggerScan).mockResolvedValue({ ...baseRun, status: "PENDING" });
    vi.mocked(getScanRun).mockResolvedValue({ ...baseRun, status: "RUNNING" });
    const onScanComplete = vi.fn();

    render(<RunScanButton onScanComplete={onScanComplete} />);
    fireEvent.click(screen.getByRole("button"));

    // 40 polls x 1.5s each -- advance one tick at a time so each
    // iteration's timer + mocked-promise resolution both get to run.
    for (let i = 0; i < 41; i++) {
      await vi.advanceTimersByTimeAsync(1500);
    }

    expect(screen.getByText(/ما زال قيد التنفيذ/)).toBeInTheDocument();
    expect(onScanComplete).not.toHaveBeenCalled();
  });

  it("shows an error message if triggering the scan itself fails", async () => {
    vi.mocked(triggerScan).mockRejectedValue(new Error("boom"));

    render(<RunScanButton />);
    fireEvent.click(screen.getByRole("button"));

    expect(await screen.findByText(/تعذّر تشغيل المسح/)).toBeInTheDocument();
  });
});
