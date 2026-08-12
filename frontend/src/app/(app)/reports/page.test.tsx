import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import ReportsPage from "./page";

/** Regression: production confirmed (2026-08-06) that this page, when
 * it was an async Server Component calling getRankings() server-side,
 * crashed with "An error occurred in the Server Components render"
 * for every real logged-in user -- apiFetch's `credentials: "include"`
 * only forwards a browser's cookies, and a Next.js Server Component's
 * fetch runs on the Node.js server with no access to the visitor's
 * session cookie at all, so the server-side call got a 401 that
 * loadTopSymbols() didn't catch (only "no_market_scan_data" was
 * handled) and re-threw. This page is now a Client Component (same
 * fix already applied to /opportunities and /dashboard for the exact
 * same reason) -- these tests lock that in by rendering it the way a
 * real browser does, through @testing-library/react, not `await`ing
 * a server render.
 */

vi.mock("@/lib/api/market", () => ({
  getRankings: vi.fn(),
}));

vi.mock("@/lib/portfolio/local-portfolio", () => ({
  getStoredPortfolioId: () => null,
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));

import { getRankings } from "@/lib/api/market";

describe("ReportsPage", () => {
  it("renders without throwing and shows the top-buy symbols once the client-side fetch resolves", async () => {
    const entry = (symbol: string) => ({
      symbol,
      sector: null,
      sector_ar: null,
      recommendation: null,
      confidence: null,
      final_score: null,
      target_price: null,
      expected_return_pct: null,
      risk_level: null,
      rank_value: null,
      current_price: null,
      stop_loss: null,
      risk_reward_ratio: null,
      time_horizon: null,
    });
    vi.mocked(getRankings).mockResolvedValue({
      scan_run_id: 81,
      rankings: [
        { category: "TOP_BUY", entries: [entry("2222"), entry("1120")], generated_at: "2026-08-06T09:00:00Z" },
      ],
    });

    render(<ReportsPage />);

    expect(await screen.findByText("2222")).toBeInTheDocument();
    expect(screen.getByText("1120")).toBeInTheDocument();
  });

  it("shows the run-a-scan empty state when no market scan data exists yet, instead of crashing", async () => {
    const { ApiError } = await import("@/lib/api/client");
    vi.mocked(getRankings).mockRejectedValue(new ApiError(404, "no_market_scan_data", "no scan yet"));

    render(<ReportsPage />);

    expect(await screen.findByText("لا توجد بيانات مسح للسوق بعد")).toBeInTheDocument();
  });

  it("shows a real error state (not a crash) when the backend call fails for any other reason", async () => {
    const { ApiError } = await import("@/lib/api/client");
    vi.mocked(getRankings).mockRejectedValue(new ApiError(401, "unauthorized", "no session"));

    render(<ReportsPage />);

    expect(await screen.findByText("تعذّر تحميل الأسهم المرشحة")).toBeInTheDocument();
  });
});
