import type { MetadataRoute } from "next";

// App Store Store publishing groundwork (2026-09-11): a real web app
// manifest is the prerequisite for both (a) "Add to Home Screen"
// installability today, on Android/Chrome and iOS/Safari, with zero
// developer-account cost, and (b) wrapping this app with a tool like
// Capacitor/PWABuilder for an actual App Store/Play Store submission
// later -- that step still needs the user's own Apple/Google developer
// accounts and cannot be done from here, but this manifest is real,
// deployable, unblocked groundwork that does not wait on it.
//
// Real 192x192/512x512 exports now exist (public/icons/), generated
// from a hand-built vector source (frontend/branding/basirah-icon.svg,
// the official logo confirmed 2026-09-12) rather than upscaling the
// old single 335x335 raster -- standard PWA tooling (Lighthouse)
// expects exactly this pair. src/app/icon.png/apple-icon.png were
// also replaced with real exports from the same source, at their own
// standard sizes (512x512, 180x180).
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "بصيرة AI — Basirah",
    short_name: "بصيرة",
    description: "الذكاء الاصطناعي لتحليل السوق السعودي — Basirah AI, Saudi market intelligence.",
    start_url: "/",
    display: "standalone",
    background_color: "#0a0e14",
    theme_color: "#0a0e14",
    lang: "ar",
    dir: "rtl",
    icons: [
      {
        src: "/icons/icon-192.png",
        sizes: "192x192",
        type: "image/png",
        purpose: "any",
      },
      {
        src: "/icons/icon-512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "any",
      },
    ],
  };
}
