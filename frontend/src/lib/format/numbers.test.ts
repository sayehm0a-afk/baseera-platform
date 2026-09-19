import { describe, expect, it } from "vitest";
import { formatNumberOrDash, formatSignedPercent } from "./numbers";

describe("formatNumberOrDash", () => {
  it("formats a real number to the requested precision", () => {
    expect(formatNumberOrDash(12.345)).toBe("12.35");
    expect(formatNumberOrDash(12.345, 1)).toBe("12.3");
  });

  it("falls back to an em dash for null/undefined", () => {
    expect(formatNumberOrDash(null)).toBe("—");
    expect(formatNumberOrDash(undefined)).toBe("—");
  });

  it("falls back to an em dash for NaN/Infinity instead of leaking them to the screen", () => {
    expect(formatNumberOrDash(NaN)).toBe("—");
    expect(formatNumberOrDash(Infinity)).toBe("—");
    expect(formatNumberOrDash(-Infinity)).toBe("—");
  });
});

describe("formatSignedPercent", () => {
  it("prefixes a non-negative value with a plus sign", () => {
    expect(formatSignedPercent(5.5)).toBe("+5.50%");
    expect(formatSignedPercent(0)).toBe("+0.00%");
  });

  it("keeps the sign for a negative value", () => {
    expect(formatSignedPercent(-3.2)).toBe("-3.20%");
  });

  it("falls back to an em dash for null/NaN", () => {
    expect(formatSignedPercent(null)).toBe("—");
    expect(formatSignedPercent(NaN)).toBe("—");
  });
});
