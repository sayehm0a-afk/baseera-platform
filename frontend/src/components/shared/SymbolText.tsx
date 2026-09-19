/** Isolates a Latin stock ticker (e.g. "AAPL") from the surrounding
 * RTL flow -- a strong-LTR run embedded in an RTL row can visually
 * reorder against adjacent Arabic text without this boundary (masked
 * everywhere a 4-digit Tadawul-only symbol was the only case that
 * existed). A no-op for every digit-only symbol. See
 * StockDirectoryRow's own comment for the original fix this
 * generalizes -- multi-market expansion, full-platform audit
 * 2026-09-19. */
export function SymbolText({ children }: { children: React.ReactNode }) {
  return <bdi dir="ltr">{children}</bdi>;
}
