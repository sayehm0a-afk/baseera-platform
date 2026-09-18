import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { buildRadarDayOptions, RadarDaySelector } from "./RadarDaySelector";

describe("buildRadarDayOptions", () => {
  it("returns exactly 7 days, oldest first, ending in today", () => {
    // 2026-09-18 12:00 UTC = 2026-09-18 15:00 Asia/Riyadh (UTC+3) -- well
    // inside the same Tadawul-local calendar day, no boundary ambiguity.
    const now = new Date("2026-09-18T12:00:00Z");
    const days = buildRadarDayOptions(now);

    expect(days).toHaveLength(7);
    expect(days[6].date).toBe("2026-09-18");
    expect(days[6].isToday).toBe(true);
    expect(days[0].date).toBe("2026-09-12");
    expect(days.filter((d) => d.isToday)).toHaveLength(1);
  });

  it("never mislabels a day close to the Tadawul-local midnight boundary", () => {
    // 2026-09-18T21:30:00Z = 2026-09-19T00:30 Asia/Riyadh -- already the
    // next Tadawul-local day even though the UTC date reads 09-18.
    const now = new Date("2026-09-18T21:30:00Z");
    const days = buildRadarDayOptions(now);
    expect(days[6].date).toBe("2026-09-19");
  });
});

describe("RadarDaySelector", () => {
  const options = buildRadarDayOptions(new Date("2026-09-18T12:00:00Z"));

  it("labels only today's tab اليوم, every other tab gets its real weekday name", () => {
    render(<RadarDaySelector value="2026-09-18" onChange={() => {}} options={options} />);
    expect(screen.getByText("اليوم")).toBeInTheDocument();
    expect(screen.queryAllByText(/الأحد|الاثنين|الثلاثاء|الأربعاء|الخميس|الجمعة|السبت/).length).toBe(6);
  });

  it("marks the selected day as active", () => {
    render(<RadarDaySelector value="2026-09-16" onChange={() => {}} options={options} />);
    const tabs = screen.getAllByRole("tab");
    const active = tabs.find((t) => t.getAttribute("aria-selected") === "true");
    expect(active).toHaveTextContent("16");
  });

  it("calls onChange with the real YYYY-MM-DD of the clicked day", () => {
    const onChange = vi.fn();
    render(<RadarDaySelector value="2026-09-18" onChange={onChange} options={options} />);

    fireEvent.click(screen.getByText("15"));

    expect(onChange).toHaveBeenCalledWith("2026-09-15");
  });
});
