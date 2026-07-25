import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AiStar } from "./AiStar";

describe("AiStar", () => {
  it("renders at the 3 approved sizes only", () => {
    const { container: sm } = render(<AiStar size="sm" />);
    const { container: md } = render(<AiStar size="md" />);
    const { container: lg } = render(<AiStar size="lg" />);

    expect(sm.querySelector("svg")).toHaveAttribute("width", "12");
    expect(md.querySelector("svg")).toHaveAttribute("width", "16");
    expect(lg.querySelector("svg")).toHaveAttribute("width", "20");
  });

  it("fills exclusively with the AI teal token, never gold", () => {
    const { container } = render(<AiStar />);
    const path = container.querySelector("path");
    expect(path).toHaveAttribute("fill", "var(--color-bsr-teal-500)");
  });

  it("is decorative (aria-hidden) unless an explicit label is given", () => {
    const { container: decorative } = render(<AiStar />);
    expect(decorative.querySelector("svg")).toHaveAttribute(
      "aria-hidden",
      "true"
    );

    const { container: labeled } = render(<AiStar label="بصيرة" />);
    expect(labeled.querySelector("svg")).toHaveAttribute(
      "aria-label",
      "بصيرة"
    );
  });
});
