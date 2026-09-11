import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  experimental: {
    // http-proxy (which the rewrite below runs on) defaults to a 30s
    // proxyTimeout -- verified empirically: a same-origin proxied
    // request to a backend that took 32s to respond came back as a
    // bare "HTTP 500 Internal Server Error" at ~30.4s, even though the
    // backend later completed the work successfully. POST /portfolio/
    // analyze processes up to PORTFOLIO_MAX_HOLDINGS (default 50)
    // holdings synchronously in one request (see
    // src/portfolio_intelligence/config.py's own "bounds request
    // latency" docstring) -- comfortably capable of exceeding 30s on a
    // large portfolio or a slow upstream data provider, well before
    // Safari or any client-side timeout would matter. 120s is a
    // deliberately generous but still-bounded ceiling (never
    // unbounded -- a hung backend must not hold a proxy connection
    // open forever); this is a starting point pending real production
    // p99 latency data for /portfolio/analyze, not a measured value.
    proxyTimeout: 120_000,
  },
  async rewrites() {
    // Keep cookies first-party in Safari. The browser calls this app;
    // Next forwards to the existing API without changing cookie paths.
    // Retain the existing Railway variable as a deployment-compatible
    // fallback; BACKEND_API_URL can replace it with a server-only setting.
    const backend = (
      process.env.BACKEND_API_URL ??
      process.env.NEXT_PUBLIC_API_BASE_URL ??
      "http://localhost:8000"
    ).replace(/\/+$/, "");

    return [
      { source: "/api/v1/:path*", destination: `${backend}/api/v1/:path*` },
      // Used by the data-health banner; do not proxy unrelated /health
      // routes or replace the frontend's own healthcheck.
      { source: "/health/market-data", destination: `${backend}/health/market-data` },
    ];
  },
  async headers() {
    // Auth pages must never be served stale. A production report after
    // the same-origin proxy fix shipped (ADR-safari-session-recovery.md)
    // showed a real, working login (verified end to end, real 200 with
    // cookies set) followed minutes later by a generic failure report on
    // the same device -- with no server-side reproduction, the leading
    // explanation is a cached pre-fix page/bundle still active in the
    // browser tab. These five routes carry no per-user data and are safe
    // to mark uncacheable outright, closing off that whole class of
    // "works only after clearing site data" reports on any future deploy.
    const noStoreRoutes = ["/login", "/register", "/forgot-password", "/reset-password", "/verify-email"];
    return noStoreRoutes.map((source) => ({
      source,
      headers: [{ key: "Cache-Control", value: "no-store, must-revalidate" }],
    }));
  },
};

export default nextConfig;
