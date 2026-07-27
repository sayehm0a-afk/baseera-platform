import { describe, expect, it } from "vitest";
import { healthBandColorClass } from "./portfolio-labels";

describe("healthBandColorClass", () => {
  it("colors EXCELLENT and GOOD as market-up", () => {
    expect(healthBandColorClass("EXCELLENT")).toBe("text-bsr-market-up");
    expect(healthBandColorClass("GOOD")).toBe("text-bsr-market-up");
  });

  it("colors FAIR as the watch action token", () => {
    expect(healthBandColorClass("FAIR")).toBe("text-bsr-action-watch");
  });

  it("colors POOR and CRITICAL as market-down", () => {
    expect(healthBandColorClass("POOR")).toBe("text-bsr-market-down");
    expect(healthBandColorClass("CRITICAL")).toBe("text-bsr-market-down");
  });

  it("never uses the AI teal token for a non-AI health band", () => {
    for (const band of ["EXCELLENT", "GOOD", "FAIR", "POOR", "CRITICAL"]) {
      expect(healthBandColorClass(band)).not.toContain("teal");
    }
  });
});
