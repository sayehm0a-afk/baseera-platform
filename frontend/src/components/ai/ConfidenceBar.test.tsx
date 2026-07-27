import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ConfidenceBar } from "./ConfidenceBar";

describe("ConfidenceBar", () => {
  it("exposes the confidence value via aria-valuenow", () => {
    render(<ConfidenceBar confidence={87} />);
    expect(screen.getByRole("progressbar")).toHaveAttribute(
      "aria-valuenow",
      "87"
    );
  });

  it("clamps values above 100", () => {
    render(<ConfidenceBar confidence={140} />);
    expect(screen.getByRole("progressbar")).toHaveAttribute(
      "aria-valuenow",
      "100"
    );
  });

  it("clamps negative values to 0", () => {
    render(<ConfidenceBar confidence={-10} />);
    expect(screen.getByRole("progressbar")).toHaveAttribute(
      "aria-valuenow",
      "0"
    );
  });
});
