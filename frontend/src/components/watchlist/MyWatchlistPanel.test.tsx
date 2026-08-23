import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { MyWatchlistPanel } from "./MyWatchlistPanel";
import type { WatchlistItem } from "@/lib/api/watchlist-types";

vi.mock("@/lib/api/watchlist", () => ({
  getMyWatchlist: vi.fn(),
  removeFromWatchlist: vi.fn(),
}));

import { getMyWatchlist, removeFromWatchlist } from "@/lib/api/watchlist";

function buildItem(overrides: Partial<WatchlistItem> = {}): WatchlistItem {
  return {
    symbol: "2222",
    added_at: "2026-08-01T12:00:00Z",
    company_name_ar: "أرامكو السعودية",
    sector_ar: "الطاقة",
    latest_decision: "BUY",
    latest_decision_label_ar: "شراء",
    latest_confidence_score: 75,
    latest_current_price: 30.5,
    latest_entry_zone_low: 30.0,
    latest_entry_zone_high: 30.6,
    latest_target_1: 32.0,
    latest_target_2: null,
    latest_target_3: null,
    latest_stop_loss: 29.0,
    latest_data_freshness_status: "LIVE",
    latest_decision_timestamp: "2026-08-01T12:00:00Z",
    radar_is_live_opportunity: false,
    radar_stage1_rank: null,
    latest_decision_freshness_status: null,
    latest_is_decision_fresh: null,
    radar_ranking_reason_ar: null,
    ...overrides,
  };
}

describe("MyWatchlistPanel", () => {
  it("shows an empty state when the user has saved nothing yet", async () => {
    vi.mocked(getMyWatchlist).mockResolvedValue({ generated_at: "2026-08-01T00:00:00Z", items: [] });

    render(<MyWatchlistPanel />);

    expect(await screen.findByText("قائمة المتابعة فارغة")).toBeInTheDocument();
  });

  it("renders real saved items with their real latest decision", async () => {
    vi.mocked(getMyWatchlist).mockResolvedValue({
      generated_at: "2026-08-01T00:00:00Z",
      items: [buildItem()],
    });

    render(<MyWatchlistPanel />);

    expect(await screen.findByText("2222")).toBeInTheDocument();
    expect(screen.getByText("أرامكو السعودية")).toBeInTheDocument();
    expect(screen.getByText("شراء")).toBeInTheDocument();
    expect(screen.getByText("ثقة 75%")).toBeInTheDocument();
  });

  it("shows 'not yet analyzed' for a symbol with no decision snapshot -- never fabricates one", async () => {
    vi.mocked(getMyWatchlist).mockResolvedValue({
      generated_at: "2026-08-01T00:00:00Z",
      items: [
        buildItem({
          latest_decision: null,
          latest_decision_label_ar: null,
          latest_confidence_score: null,
          latest_current_price: null,
        }),
      ],
    });

    render(<MyWatchlistPanel />);

    expect(await screen.findByText("لم يتم تحليل هذا السهم بعد.")).toBeInTheDocument();
  });

  it("shows a live radar badge and ranking reason for a symbol on the radar", async () => {
    vi.mocked(getMyWatchlist).mockResolvedValue({
      generated_at: "2026-08-01T00:00:00Z",
      items: [
        buildItem({
          radar_is_live_opportunity: true,
          radar_stage1_rank: 2,
          radar_ranking_reason_ar: "اختراق مستوى المقاومة بحجم تداول مرتفع",
        }),
      ],
    });

    render(<MyWatchlistPanel />);

    expect(await screen.findByText("فرصة حية في الرادار الذكي · الترتيب #2")).toBeInTheDocument();
    expect(screen.getByText("اختراق مستوى المقاومة بحجم تداول مرتفع")).toBeInTheDocument();
  });

  it("does not show the radar badge for a symbol not currently on the radar", async () => {
    vi.mocked(getMyWatchlist).mockResolvedValue({
      generated_at: "2026-08-01T00:00:00Z",
      items: [buildItem()],
    });

    render(<MyWatchlistPanel />);
    await screen.findByText("2222");

    expect(screen.queryByText(/الرادار الذكي/)).not.toBeInTheDocument();
  });

  it("shows the recommendation age alongside the decision", async () => {
    vi.mocked(getMyWatchlist).mockResolvedValue({
      generated_at: "2026-08-01T00:00:00Z",
      items: [buildItem({ latest_decision_timestamp: "2026-08-01T12:00:00Z" })],
    });

    render(<MyWatchlistPanel />);

    expect(await screen.findByText(/آخر تحديث:/)).toBeInTheDocument();
  });

  it("never shows target/stop without a visible recommendation age -- a decision with no timestamp shows neither", async () => {
    vi.mocked(getMyWatchlist).mockResolvedValue({
      generated_at: "2026-08-01T00:00:00Z",
      items: [buildItem({ latest_decision_timestamp: null })],
    });

    render(<MyWatchlistPanel />);
    await screen.findByText("2222");

    expect(screen.queryByText(/الهدف الأول:/)).not.toBeInTheDocument();
    expect(screen.queryByText(/وقف الخسارة:/)).not.toBeInTheDocument();
    expect(screen.queryByText(/آخر تحديث:/)).not.toBeInTheDocument();
  });

  it("shows target/stop together with their age when a timestamp is present", async () => {
    vi.mocked(getMyWatchlist).mockResolvedValue({
      generated_at: "2026-08-01T00:00:00Z",
      items: [buildItem({ latest_decision_timestamp: "2026-08-01T12:00:00Z" })],
    });

    render(<MyWatchlistPanel />);

    expect(await screen.findByText(/الهدف الأول:/)).toBeInTheDocument();
    expect(screen.getByText(/آخر تحديث:/)).toBeInTheDocument();
  });

  it("shows an error state when the fetch fails", async () => {
    vi.mocked(getMyWatchlist).mockRejectedValue(new Error("network error"));

    render(<MyWatchlistPanel />);

    expect(await screen.findByText("تعذّر تحميل قائمة المتابعة")).toBeInTheDocument();
  });

  it("removes an item from the list after a successful remove", async () => {
    vi.mocked(getMyWatchlist).mockResolvedValue({
      generated_at: "2026-08-01T00:00:00Z",
      items: [buildItem()],
    });
    vi.mocked(removeFromWatchlist).mockResolvedValue({ message: "removed" });

    render(<MyWatchlistPanel />);
    await screen.findByText("2222");

    fireEvent.click(screen.getByRole("button", { name: "إزالة" }));

    await waitFor(() => expect(screen.queryByText("2222")).not.toBeInTheDocument());
    expect(removeFromWatchlist).toHaveBeenCalledWith("2222");
  });
});
