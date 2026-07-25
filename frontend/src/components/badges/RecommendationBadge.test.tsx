import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { RecommendationBadge } from "./RecommendationBadge";

describe("RecommendationBadge", () => {
  it("renders the Arabic label for BUY", () => {
    render(<RecommendationBadge value="BUY" />);
    expect(screen.getByText("شراء")).toBeInTheDocument();
  });

  it("renders the Arabic label for WATCH", () => {
    render(<RecommendationBadge value="WATCH" />);
    expect(screen.getByText("مراقبة")).toBeInTheDocument();
  });

  it("colors BUY with the buy action token, never teal", () => {
    render(<RecommendationBadge value="BUY" />);
    const badge = screen.getByText("شراء");
    expect(badge.className).toContain("bsr-action-buy");
    expect(badge.className).not.toContain("teal");
  });

  it("colors SELL with the sell action token", () => {
    render(<RecommendationBadge value="SELL" />);
    expect(screen.getByText("بيع").className).toContain("bsr-action-sell");
  });
});
