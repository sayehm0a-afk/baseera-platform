import { describe, expect, it } from "vitest";
import {
  RANKING_CATEGORY_LABELS,
  RANKING_CATEGORY_ORDER,
  WATCHLIST_CATEGORY_LABELS,
  WATCHLIST_CATEGORY_ORDER,
} from "./market-intelligence-labels";

describe("market intelligence category labels", () => {
  it("has exactly the 17 ranking categories the backend defines", () => {
    expect(RANKING_CATEGORY_ORDER).toHaveLength(17);
    expect(new Set(RANKING_CATEGORY_ORDER).size).toBe(17);
  });

  it("has exactly the 9 watchlist categories the backend defines", () => {
    expect(WATCHLIST_CATEGORY_ORDER).toHaveLength(9);
    expect(new Set(WATCHLIST_CATEGORY_ORDER).size).toBe(9);
  });

  it("every ranking category has a non-empty Arabic label", () => {
    for (const category of RANKING_CATEGORY_ORDER) {
      expect(RANKING_CATEGORY_LABELS[category]).toBeTruthy();
    }
  });

  it("every watchlist category has a non-empty Arabic label", () => {
    for (const category of WATCHLIST_CATEGORY_ORDER) {
      expect(WATCHLIST_CATEGORY_LABELS[category]).toBeTruthy();
    }
  });
});
