import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ChartRangeTabs, rangeCutoffDate } from "./ChartRangeTabs";

describe("ChartRangeTabs", () => {
  it("renders every real range option and never an intraday اليوم tab", () => {
    render(<ChartRangeTabs value="3M" onChange={() => {}} />);

    expect(screen.getByRole("tab", { name: "أسبوع" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "شهر" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "3 أشهر" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "6 أشهر" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "سنة" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "الكل" })).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "اليوم" })).not.toBeInTheDocument();
  });

  it("marks the active range as selected", () => {
    render(<ChartRangeTabs value="1Y" onChange={() => {}} />);
    expect(screen.getByRole("tab", { name: "سنة" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "3 أشهر" })).toHaveAttribute("aria-selected", "false");
  });

  it("calls onChange with the clicked range", () => {
    let selected: string | null = null;
    render(<ChartRangeTabs value="3M" onChange={(range) => (selected = range)} />);

    fireEvent.click(screen.getByRole("tab", { name: "سنة" }));

    expect(selected).toBe("1Y");
  });
});

describe("rangeCutoffDate", () => {
  const latest = new Date("2026-09-18T00:00:00Z");

  it("returns null for ALL -- never a fixed cutoff for the full loaded history", () => {
    expect(rangeCutoffDate("ALL", latest)).toBeNull();
  });

  it("computes a real calendar cutoff for a fixed window", () => {
    const cutoff = rangeCutoffDate("1M", latest);
    expect(cutoff).not.toBeNull();
    expect(cutoff!.getUTCDate()).toBe(19); // 30 days before 2026-09-18 -> 2026-08-19
    expect(cutoff!.getUTCMonth()).toBe(7); // August (0-indexed)
  });
});
