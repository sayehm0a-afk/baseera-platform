import type { NextConfig } from "next";

const nextConfig: NextConfig = {
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
