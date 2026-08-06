import type { Metadata, Viewport } from "next";
import { IBM_Plex_Sans_Arabic, Inter } from "next/font/google";
import "./globals.css";

const ibmPlexSansArabic = IBM_Plex_Sans_Arabic({
  variable: "--font-ibm-plex-sans-arabic",
  subsets: ["arabic", "latin"],
  weight: ["400", "500", "600", "700"],
  display: "swap",
});

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  display: "swap",
});

// The single source of truth for Basirah's public-facing URL --
// read from an env var, never hardcoded, so switching from the
// temporary Railway URL to the official domain (Mandate 8) is a
// config change, not a code change. Falls back to localhost only for
// local dev, where absolute metadata URLs don't matter.
const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";

const TITLE = "بصيرة AI | Basirah — Saudi Market Intelligence";
const DESCRIPTION =
  "الذكاء الاصطناعي لتحليل السوق السعودي — Basirah AI, Saudi market intelligence.";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: TITLE,
  description: DESCRIPTION,
  alternates: {
    canonical: "/",
  },
  openGraph: {
    title: TITLE,
    description: DESCRIPTION,
    url: SITE_URL,
    siteName: "Basirah",
    locale: "ar_SA",
    type: "website",
    images: [{ url: "/icon.png", width: 335, height: 335, alt: "Basirah" }],
  },
  twitter: {
    card: "summary",
    title: TITLE,
    description: DESCRIPTION,
    images: ["/icon.png"],
  },
};

export const viewport: Viewport = {
  themeColor: "#0a0e14",
  colorScheme: "dark",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="ar"
      dir="rtl"
      className={`${ibmPlexSansArabic.variable} ${inter.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col bg-bsr-surface-base text-bsr-text-primary">
        {children}
      </body>
    </html>
  );
}
