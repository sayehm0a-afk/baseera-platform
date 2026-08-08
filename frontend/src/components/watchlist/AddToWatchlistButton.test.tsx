import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AddToWatchlistButton } from "./AddToWatchlistButton";
import { ApiError } from "@/lib/api/client";

vi.mock("@/lib/api/watchlist", () => ({
  addToWatchlist: vi.fn(),
}));

import { addToWatchlist } from "@/lib/api/watchlist";

describe("AddToWatchlistButton", () => {
  it("shows a saved state after a successful add", async () => {
    vi.mocked(addToWatchlist).mockResolvedValue({
      symbol: "2222",
      added_at: "2026-08-01T00:00:00Z",
      company_name_ar: null,
      sector_ar: null,
      latest_decision: null,
      latest_decision_label_ar: null,
      latest_confidence_score: null,
      latest_current_price: null,
      latest_entry_zone_low: null,
      latest_entry_zone_high: null,
      latest_target_1: null,
      latest_target_2: null,
      latest_target_3: null,
      latest_stop_loss: null,
      latest_data_freshness_status: null,
      latest_decision_timestamp: null,
    });

    render(<AddToWatchlistButton symbol="2222" />);
    fireEvent.click(screen.getByRole("button", { name: "أضف إلى قائمة المتابعة" }));

    expect(await screen.findByRole("button", { name: "أُضيف إلى قائمة المتابعة" })).toBeDisabled();
    expect(addToWatchlist).toHaveBeenCalledWith("2222");
  });

  it("treats an already-saved symbol as success, not an error", async () => {
    vi.mocked(addToWatchlist).mockRejectedValue(new ApiError(409, "watchlist_item_already_exists", "already saved"));

    render(<AddToWatchlistButton symbol="2222" />);
    fireEvent.click(screen.getByRole("button", { name: "أضف إلى قائمة المتابعة" }));

    expect(await screen.findByRole("button", { name: "أُضيف إلى قائمة المتابعة" })).toBeInTheDocument();
    expect(screen.queryByText("تعذّرت الإضافة إلى قائمة المتابعة.")).not.toBeInTheDocument();
  });

  it("shows a real error message on genuine failure", async () => {
    vi.mocked(addToWatchlist).mockRejectedValue(new ApiError(500, "internal_error", "boom"));

    render(<AddToWatchlistButton symbol="2222" />);
    fireEvent.click(screen.getByRole("button", { name: "أضف إلى قائمة المتابعة" }));

    await waitFor(() =>
      expect(screen.getByText("تعذّرت الإضافة إلى قائمة المتابعة.")).toBeInTheDocument()
    );
  });
});
