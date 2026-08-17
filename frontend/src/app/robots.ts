import type { MetadataRoute } from "next";

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";

// Everything under the (app) route group requires an authenticated
// session -- crawlers can't reach it anyway (they'd just hit the login
// redirect), but disallowing it explicitly keeps search results honest
// and keeps /owner/* (admin-only) out of any crawl attempt entirely.
export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: "*",
      allow: ["/", "/login", "/register", "/forgot-password"],
      disallow: [
        "/dashboard",
        "/today",
        "/radar",
        "/scan",
        "/watchlist",
        "/opportunities",
        "/portfolio",
        "/ai",
        "/news",
        "/reports",
        "/strategies",
        "/settings",
        "/stocks",
        "/owner",
        "/reset-password",
        "/verify-email",
      ],
    },
    sitemap: `${SITE_URL}/sitemap.xml`,
  };
}
