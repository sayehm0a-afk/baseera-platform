import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { RunScanButton } from "./RunScanButton";
import { getScanRun, triggerScan } from "@/lib/api/market";

const { refresh } = vi.hoisted(() => ({ refresh: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));
vi.mock("@/lib/api/market", () => ({ getScanRun: vi.fn(), triggerScan: vi.fn() }));

function run(status: string) {
  return { id: 17, status } as Awaited<ReturnType<typeof getScanRun>>;
}

async function start() {
  render(<RunScanButton />);
  await act(async () => { fireEvent.click(screen.getByRole("button")); });
}

describe("RunScanButton completion evidence", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
    vi.mocked(triggerScan).mockResolvedValue(run("RUNNING"));
  });
  afterEach(() => vi.useRealTimers());

  it("refreshes only after confirmed success", async () => {
    vi.mocked(getScanRun).mockResolvedValue(run("SUCCESS"));
    await start();
    await act(async () => { await vi.advanceTimersByTimeAsync(1500); });
    expect(refresh).toHaveBeenCalledTimes(1);
    expect(triggerScan).toHaveBeenCalledTimes(1);
  });

  it("shows failure without treating it as a new result", async () => {
    vi.mocked(getScanRun).mockResolvedValue(run("FAILED"));
    await start();
    await act(async () => { await vi.advanceTimersByTimeAsync(1500); });
    expect(screen.getByRole("alert").textContent).toContain("لم ينجح المسح");
    expect(refresh).not.toHaveBeenCalled();
    expect(getScanRun).toHaveBeenCalledTimes(1);
  });

  it("discloses timeout without triggering another scan", async () => {
    vi.mocked(getScanRun).mockResolvedValue(run("RUNNING"));
    await start();
    await act(async () => { await vi.advanceTimersByTimeAsync(60000); });
    expect(screen.getByRole("status").textContent).toContain("قد يكون مستمرًا");
    expect(getScanRun).toHaveBeenCalledTimes(40);
    expect(triggerScan).toHaveBeenCalledTimes(1);
    expect(refresh).not.toHaveBeenCalled();
  });

  it("shows a connection error without claiming success", async () => {
    vi.mocked(getScanRun).mockRejectedValue(new Error("offline"));
    await start();
    await act(async () => { await vi.advanceTimersByTimeAsync(1500); });
    expect(screen.getByText(/تعذّر تشغيل المسح/)).toBeDefined();
    expect(refresh).not.toHaveBeenCalled();
  });
});
