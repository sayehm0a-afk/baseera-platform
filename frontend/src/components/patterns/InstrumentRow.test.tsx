import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { InstrumentRow } from "./InstrumentRow";

/** Decision Engine V2 rollout: the Scan page's shared instrument row
 * must prefer the gate-checked V2 badge over the legacy
 * RecommendationBadge whenever both decision and decision_label_ar
 * are present, exactly as the stock detail page already does. */

describe("InstrumentRow", () => {
  it("renders the Decision Engine V2 badge instead of the legacy recommendation badge when both decision and decision_label_ar are present", () => {
    render(
      <InstrumentRow
        symbol="2222"
        recommendation="BUY"
        decision="BUY_CANDIDATE"
        decisionLabelAr="مرشح للشراء"
      />
    );
    expect(screen.getByText("مرشح للشراء")).toBeInTheDocument();
    expect(screen.queryByText("شراء")).not.toBeInTheDocument();
  });

  it("falls back to the legacy recommendation badge when V2 decision data is absent", () => {
    render(<InstrumentRow symbol="2222" recommendation="BUY" />);
    expect(screen.getByText("شراء")).toBeInTheDocument();
    expect(screen.queryByText("مرشح للشراء")).not.toBeInTheDocument();
  });

  it("renders no badge at all when neither V2 decision data nor a legacy recommendation is provided", () => {
    render(<InstrumentRow symbol="2222" />);
    expect(screen.queryByText("مرشح للشراء")).not.toBeInTheDocument();
    expect(screen.queryByText("شراء")).not.toBeInTheDocument();
  });
});
