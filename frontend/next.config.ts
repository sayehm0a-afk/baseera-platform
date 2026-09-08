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
};

export default nextConfig;
