/** Shared "real number, or an honest dash" formatting -- extracted so
 * the same rule (never fabricate a value, never leak "null"/"NaN" to
 * the screen) lives in one place instead of being reimplemented per
 * component (portfolio/page.tsx and HoldingRow.tsx previously each had
 * their own copy). */

export function formatNumberOrDash(value: number | null | undefined, digits = 2): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return value.toFixed(digits);
}

/** Same as `formatNumberOrDash`, prefixed with an explicit "+" for a
 * non-negative value (P&L-style figures where the sign itself is the
 * signal, not just the magnitude). */
export function formatSignedPercent(value: number | null | undefined, digits = 2): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return `${value >= 0 ? "+" : ""}${value.toFixed(digits)}%`;
}
