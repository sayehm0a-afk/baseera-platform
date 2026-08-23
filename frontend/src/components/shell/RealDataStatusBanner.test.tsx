import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { RealDataStatusBanner } from "./RealDataStatusBanner";
import type { MarketDataHealth, MarketStatus } from "@/lib/api/types";

/** Production truthfulness fix (2026-08-23): real production evidence
 * showed `can_publish_recommendations: false` moments after a fully
 * successful SAHMK ingestion run -- `current_provider_kind` and
 * `last_connectivity_status` were simply `null` (no worker had made a
 * recent provider-selection call), not a recorded failure. The banner
 * must not render the same "تعذر الحصول على بيانات حقيقية" (confirmed
 * failure) message for that case as it does for a genuinely observed
 * failure -- see `provider_state` on GET /health/market-data. */

vi.mock("@/lib/api/market", () => ({
  getMarketDataHealth: vi.fn(),
  getMarketStatus: vi.fn(),
}));

import { getMarketDataHealth, getMarketStatus } from "@/lib/api/market";

function health(overrides: Partial<MarketDataHealth> = {}): MarketDataHealth {
  return {
    configured_provider: "sahmk",
    strict_real_data: true,
    synthetic_allowed: false,
    sahmk_key_present: true,
    current_provider_kind: null,
    last_connectivity_status: null,
    last_connectivity_at: null,
    last_real_data_at: null,
    last_scan_source: null,
    can_publish_recommendations: false,
    provider_state: "UNKNOWN_NO_RECENT_CHECK",
    ...overrides,
  };
}

describe("RealDataStatusBanner", () => {
  beforeEach(() => {
    vi.mocked(getMarketDataHealth).mockReset();
    vi.mocked(getMarketStatus).mockReset();
  });

  it("does not render the confirmed-failure message when no failure has actually been observed (provider_state=UNKNOWN_NO_RECENT_CHECK)", async () => {
    vi.mocked(getMarketDataHealth).mockResolvedValue(health());

    render(<RealDataStatusBanner />);

    await waitFor(() => {
      expect(screen.getByText(/لم يتم التحقق من الاتصال بمزود البيانات مؤخرًا/)).toBeInTheDocument();
    });
    expect(screen.queryByText(/تعذر الحصول على بيانات حقيقية/)).not.toBeInTheDocument();
  });

  it("renders the confirmed-failure message only for a real observed failure (provider_state=CONFIRMED_UNAVAILABLE)", async () => {
    vi.mocked(getMarketDataHealth).mockResolvedValue(
      health({ current_provider_kind: "dev", last_connectivity_status: "FAILED", provider_state: "CONFIRMED_UNAVAILABLE" })
    );

    render(<RealDataStatusBanner />);

    await waitFor(() => {
      expect(screen.getByText(/تعذر الحصول على بيانات حقيقية من مزود البيانات/)).toBeInTheDocument();
    });
  });

  it("renders the normal market-status banner when the provider is confirmed live", async () => {
    vi.mocked(getMarketDataHealth).mockResolvedValue(
      health({ current_provider_kind: "sahmk", last_connectivity_status: "SUCCESS", can_publish_recommendations: true, provider_state: "CONFIRMED_LIVE" })
    );
    const marketStatus: MarketStatus = {
      status: "OPEN",
      label_ar: "السوق مفتوح",
      is_trading_day: true,
      server_time_riyadh: "2026-08-23T13:00:00Z",
      seconds_until_next_open: 0,
      seconds_until_close: 3600,
      last_completed_session_date: null,
      provider_connected: true,
      holiday_calendar_disclosed_gap: "",
    };
    vi.mocked(getMarketStatus).mockResolvedValue(marketStatus);

    render(<RealDataStatusBanner />);

    await waitFor(() => {
      expect(screen.getByText("السوق مفتوح")).toBeInTheDocument();
    });
    expect(screen.queryByText(/تعذر الحصول على بيانات حقيقية/)).not.toBeInTheDocument();
    expect(screen.queryByText(/لم يتم التحقق من الاتصال/)).not.toBeInTheDocument();
  });
});
