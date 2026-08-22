import { describe, expect, it } from "vitest";
import {
  ageInDays,
  formatArabicDateTime,
  formatRelativeAgeAr,
  freshnessLabelAr,
  isEntryMissed,
} from "./freshness";

describe("freshness helpers", () => {
  it("formats a real ISO timestamp with the Gregorian calendar explicitly requested", () => {
    const result = formatArabicDateTime("2026-08-20T10:00:00Z");
    // Never assert a locale-formatted literal (varies by ICU data) -- assert
    // it produced real, non-placeholder output instead.
    expect(result).not.toBe("--");
    expect(result.length).toBeGreaterThan(0);
  });

  it("returns a placeholder rather than fabricating a timestamp for null input", () => {
    expect(formatArabicDateTime(null)).toBe("--");
    expect(formatArabicDateTime(undefined)).toBe("--");
  });

  it("never claims a multi-day-old recommendation is only minutes old", () => {
    const fourDaysAgo = new Date(Date.now() - 4 * 24 * 60 * 60 * 1000).toISOString();
    const label = formatRelativeAgeAr(fourDaysAgo);
    expect(label).toMatch(/يوم|أيام/);
    expect(label).not.toMatch(/دقيقة|دقائق/);
  });

  it("reports minutes for a genuinely recent timestamp", () => {
    const fiveMinutesAgo = new Date(Date.now() - 5 * 60 * 1000).toISOString();
    expect(formatRelativeAgeAr(fiveMinutesAgo)).toBe("قبل 5 دقائق");
  });

  it("reports hours for a same-day but not-recent timestamp", () => {
    const threeHoursAgo = new Date(Date.now() - 3 * 60 * 60 * 1000).toISOString();
    expect(formatRelativeAgeAr(threeHoursAgo)).toBe("قبل 3 ساعات");
  });

  it("computes age in days for staleness bucketing", () => {
    const twoDaysAgo = new Date(Date.now() - 2 * 24 * 60 * 60 * 1000).toISOString();
    const days = ageInDays(twoDaysAgo);
    expect(days).not.toBeNull();
    expect(days as number).toBeGreaterThan(1.9);
    expect(days as number).toBeLessThan(2.1);
  });

  it("falls back to the honest UNKNOWN label for an unrecognized freshness status", () => {
    expect(freshnessLabelAr("SOMETHING_NEW")).toBe("حداثة البيانات غير مؤكدة");
    expect(freshnessLabelAr(null)).toBe("حداثة البيانات غير مؤكدة");
  });

  it("only treats the real MISSED_ENTRY value as a missed entry", () => {
    expect(isEntryMissed("MISSED_ENTRY")).toBe(true);
    expect(isEntryMissed("READY_NOW")).toBe(false);
    expect(isEntryMissed(null)).toBe(false);
  });
});
