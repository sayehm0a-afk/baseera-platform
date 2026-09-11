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
// Reuses the existing icon.png (335x335, see src/app/icon.png) rather
// than fabricating icon files at sizes that don't exist on disk --
// standard PWA tooling (Lighthouse) prefers a 192x192/512x512 pair,
// which can be added once real square exports at those sizes exist;
// declaring sizes that don't match a real file would be worse than
// declaring the one real size honestly.
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
        src: "/icon.png",
        sizes: "335x335",
        type: "image/png",
        purpose: "any",
      },
    ],
  };
}
