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
  it("formats a real multiple/currency ratio to 2 decimal places, unscaled", () => {
    expect(formatRatioValue("current_ratio", 1.235)).toBe("1.24");
    expect(formatRatioValue("debt_to_equity", 0.823)).toBe("0.82");
    expect(formatRatioValue("price_to_earnings", 12.3)).toBe("12.30");
  });

  it("falls back to em-dash for a missing ratio", () => {
    expect(formatRatioValue("current_ratio", null)).toBe("—");
  });

  it("scales a real fraction to a percentage for every percentage-natured ratio key", () => {
    // src/analysis/fundamental/ratios/profitability.py's return_on_equity()
    // returns a raw fraction (0.174 for a real 17.4% ROE) -- this must
    // render as "17.40%", never the bare "0.17" a strong company's real
    // ROE was showing before this fix.
    expect(formatRatioValue("return_on_equity", 0.174)).toBe("17.40%");
    expect(formatRatioValue("net_profit_margin", 0.05)).toBe("5.00%");
    expect(formatRatioValue("gross_profit_margin", 0.42)).toBe("42.00%");
    expect(formatRatioValue("return_on_assets", 0.081)).toBe("8.10%");
    expect(formatRatioValue("dividend_yield", 0.032)).toBe("3.20%");
    expect(formatRatioValue("revenue_growth", -0.015)).toBe("-1.50%");
    expect(formatRatioValue("net_income_growth", 0.2)).toBe("20.00%");
    expect(formatRatioValue("eps_growth", 0.1)).toBe("10.00%");
  });
});
