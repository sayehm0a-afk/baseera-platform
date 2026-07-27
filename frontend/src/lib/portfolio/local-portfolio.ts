/**
 * The backend has no "list my portfolios" endpoint and no
 * user-to-portfolio linkage yet (`/api/v1/portfolio/*` only supports
 * analyze-by-id / read-by-id -- see src/api/routes/portfolio.py). This
 * module only remembers, on this device, which real portfolio_id the
 * user last analyzed -- every number rendered from that id still comes
 * from the real backend snapshot. Replace with a proper "my
 * portfolios" list the moment that backend endpoint exists.
 */

const STORAGE_KEY = "basirah.active-portfolio-id";

export function getStoredPortfolioId(): number | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(STORAGE_KEY);
  if (!raw) return null;
  const parsed = Number(raw);
  return Number.isFinite(parsed) ? parsed : null;
}

export function setStoredPortfolioId(id: number): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(STORAGE_KEY, String(id));
}

export function clearStoredPortfolioId(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(STORAGE_KEY);
}
