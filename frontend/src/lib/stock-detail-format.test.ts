import { describe, expect, it } from "vitest";
import { formatIndicatorValue, formatRatioValue } from "./stock-detail-format";

describe("formatIndicatorValue", () => {
  it("formats a plain number to 2 decimal places", () => {
    expect(formatIndicatorValue(47.6789)).toBe("47.68");
  });

  it("formats a compound object (e.g. MACD) as key: value pairs", () => {
    const macd = { macd_line: -0.0063, signal_line: -0.0317, histogram: 0.0254 };
    expect(formatIndicatorValue(macd)).toBe(
      "macd_line: -0.01  ·  signal_line: -0.03  ·  histogram: 0.03"
    );
  });

  it("falls back to em-dash for null/undefined", () => {
    expect(formatIndicatorValue(null)).toBe("—");
    expect(formatIndicatorValue(undefined)).toBe("—");
  });

  it("stringifies a non-numeric, non-object value as-is", () => {
    expect(formatIndicatorValue("uptrend")).toBe("uptrend");
  });
});

describe("formatRatioValue", () => {
  it("formats a plain number to 2 decimal places", () => {
    expect(formatRatioValue(12.3)).toBe("12.30");
  });

  it("falls back to em-dash for a missing ratio", () => {
    expect(formatRatioValue(null)).toBe("—");
  });
});
