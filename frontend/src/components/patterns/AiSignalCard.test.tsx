import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AiSignalCard } from "./AiSignalCard";

/** Phase 2 Foundation Cleanup, goal 4: production-grade coverage for
 * the one shared "AI signal" card reused by the dashboard, Opportunities,
 * Scan, and the owner live-test page (UI Spec Global Invariants §0) --
 * a regression here would silently break all four screens at once. */

describe("AiSignalCard", () => {
  it("renders the symbol, sector, and recommendation badge", () => {
    render(<AiSignalCard symbol="2222" sector="الطاقة" recommendation="BUY" />);
    expect(screen.getByText("2222")).toBeInTheDocument();
    expect(screen.getByText("الطاقة")).toBeInTheDocument();
    expect(screen.getByText("شراء")).toBeInTheDocument();
  });

  it("omits the sector line entirely when no sector is provided, rather than rendering an empty one", () => {
    render(<AiSignalCard symbol="2222" recommendation="BUY" />);
    expect(screen.queryByText("الطاقة")).not.toBeInTheDocument();
  });

  it("renders the confidence percentage and bar only when confidence is provided", () => {
    const { rerender } = render(<AiSignalCard symbol="2222" recommendation="BUY" confidence={82.4} />);
    expect(screen.getByText("82%")).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toBeInTheDocument();

    rerender(<AiSignalCard symbol="2222" recommendation="BUY" />);
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
  });

  it("renders the target price and colors a positive expected return with the up token", () => {
    render(<AiSignalCard symbol="2222" recommendation="BUY" targetPrice={30.5} expectedReturnPct={4.2} />);
    expect(screen.getByText("الهدف: 30.50")).toBeInTheDocument();
    const returnEl = screen.getByText("+4.2%");
    expect(returnEl.className).toContain("bsr-market-up");
  });

  it("colors a negative expected return with the down token, without the leading plus sign", () => {
    render(<AiSignalCard symbol="2222" recommendation="SELL" expectedReturnPct={-3.1} />);
    const returnEl = screen.getByText("-3.1%");
    expect(returnEl.className).toContain("bsr-market-down");
  });

  it("renders the current price and stop loss with the sell token on the stop", () => {
    render(<AiSignalCard symbol="2222" recommendation="HOLD" currentPrice={27.1} stopLoss={26.46} />);
    expect(screen.getByText("27.10")).toBeInTheDocument();
    const stopEl = screen.getByText("26.46");
    expect(stopEl.className).toContain("bsr-action-sell");
  });

  it("renders risk/reward, time horizon, and risk level using the shared Arabic label maps", () => {
    render(
      <AiSignalCard
        symbol="2222"
        recommendation="BUY"
        riskRewardRatio={2.5}
        timeHorizon="MEDIUM_TERM"
        riskLevel="HIGH"
      />
    );
    expect(screen.getByText("1:2.5")).toBeInTheDocument();
    expect(screen.getByText("المدة: متوسط المدى")).toBeInTheDocument();
    expect(screen.getByText("المخاطرة: مرتفعة")).toBeInTheDocument();
  });

  it("falls back to the raw value for an unmapped time horizon/risk level instead of rendering nothing", () => {
    render(<AiSignalCard symbol="2222" recommendation="BUY" timeHorizon="UNMAPPED_VALUE" />);
    expect(screen.getByText("المدة: UNMAPPED_VALUE")).toBeInTheDocument();
  });

  it("renders exactly two action links to the full analysis and to the chart anchor when href is provided", () => {
    render(<AiSignalCard symbol="2222" recommendation="BUY" href="/stocks/2222" />);
    const fullAnalysisLink = screen.getByRole("link", { name: "عرض التحليل الكامل" });
    const chartLink = screen.getByRole("link", { name: "فتح الشارت" });
    expect(fullAnalysisLink).toHaveAttribute("href", "/stocks/2222");
    expect(chartLink).toHaveAttribute("href", "/stocks/2222#chart");
  });

  it("renders no links at all when href is omitted", () => {
    render(<AiSignalCard symbol="2222" recommendation="BUY" />);
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });
});
