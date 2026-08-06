import type { MetadataRoute } from "next";

// Only the genuinely public, unauthenticated routes belong here --
// everything under the (app) route group requires a session and must
// not be offered to crawlers as a real destination (see robots.ts's
// disallow list, which excludes it explicitly).
const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";

export default function sitemap(): MetadataRoute.Sitemap {
  const now = new Date();
  return [
    { url: `${SITE_URL}/`, lastModified: now, changeFrequency: "weekly", priority: 1 },
    { url: `${SITE_URL}/login`, lastModified: now, changeFrequency: "yearly", priority: 0.5 },
    { url: `${SITE_URL}/register`, lastModified: now, changeFrequency: "yearly", priority: 0.5 },
  ];
}
