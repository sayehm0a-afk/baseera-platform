import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { WatchlistNewsAlertsSection } from "./WatchlistNewsAlertsSection";
import type { WatchlistNewsAlert } from "@/lib/api/watchlist-types";

vi.mock("@/lib/api/watchlist", () => ({
  getWatchlistNewsAlerts: vi.fn(),
  refreshWatchlistNewsAlerts: vi.fn(),
}));

import { getWatchlistNewsAlerts, refreshWatchlistNewsAlerts } from "@/lib/api/watchlist";

function alert(overrides: Partial<WatchlistNewsAlert> = {}): WatchlistNewsAlert {
  return {
    id: 1,
    watchlist_id: 1,
    symbol: "2222",
    news_event_id: 1,
    alert_type: "HIGH_RISK",
    severity: "CRITICAL",
    message: "High risk for 2222: lawsuit filed.",
    message_ar: null,
    generated_at: "2026-08-18T00:00:00Z",
    acknowledged_at: null,
    ...overrides,
  };
}

describe("WatchlistNewsAlertsSection", () => {
  it("shows an honest empty state when there are no alerts yet", async () => {
    vi.mocked(getWatchlistNewsAlerts).mockResolvedValue({ alerts: [] });

    render(<WatchlistNewsAlertsSection />);

    expect(await screen.findByText("لا توجد تنبيهات أخبار حالياً لأسهم قائمة المتابعة")).toBeInTheDocument();
  });

  it("renders real persisted alerts on load, never fabricated ones", async () => {
    vi.mocked(getWatchlistNewsAlerts).mockResolvedValue({ alerts: [alert()] });

    render(<WatchlistNewsAlertsSection />);

    expect(await screen.findByText("2222")).toBeInTheDocument();
    expect(screen.getByText("High risk for 2222: lawsuit filed.")).toBeInTheDocument();
    expect(screen.getByText("مخاطرة عالية")).toBeInTheDocument();
  });

  it("prefers the Arabic message when the backend supplied one, over the legacy English text", async () => {
    vi.mocked(getWatchlistNewsAlerts).mockResolvedValue({
      alerts: [alert({ message_ar: "مخاطرة عالية لسهم 2222: تم رفع قضية قانونية." })],
    });

    render(<WatchlistNewsAlertsSection />);

    expect(await screen.findByText("مخاطرة عالية لسهم 2222: تم رفع قضية قانونية.")).toBeInTheDocument();
    expect(screen.queryByText("High risk for 2222: lawsuit filed.")).not.toBeInTheDocument();
  });

  it("refreshes and reloads real alerts on the explicit action, never on mount", async () => {
    vi.mocked(getWatchlistNewsAlerts)
      .mockResolvedValueOnce({ alerts: [] })
      .mockResolvedValueOnce({ alerts: [alert()] });
    vi.mocked(refreshWatchlistNewsAlerts).mockResolvedValue({ alerts: [alert()] });

    render(<WatchlistNewsAlertsSection />);
    await screen.findByText("لا توجد تنبيهات أخبار حالياً لأسهم قائمة المتابعة");

    fireEvent.click(screen.getByText("تحديث التنبيهات"));

    await waitFor(() => expect(refreshWatchlistNewsAlerts).toHaveBeenCalled());
    expect(await screen.findByText("2222")).toBeInTheDocument();
  });

  it("shows a real error message instead of a silent blank state", async () => {
    vi.mocked(getWatchlistNewsAlerts).mockRejectedValue(new Error("network error"));

    render(<WatchlistNewsAlertsSection />);

    expect(await screen.findByText("تعذّر تحميل تنبيهات الأخبار.")).toBeInTheDocument();
  });
});
