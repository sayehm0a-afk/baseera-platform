/** Minimal generic line icons for primary navigation. Placeholders in
 * the sense that no dedicated icon-export file was supplied for these
 * (only the logo/star/app-icon assets were) -- these are ordinary UI
 * iconography, not brand marks, so they are safe to implement directly
 * rather than escalate; swap for a literal icon export if one arrives. */

const PATHS: Record<string, string> = {
  home: "M3 11l9-7 9 7v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1v-9Z",
  scan: "M4 4h4M4 4v4M20 4h-4M20 4v4M4 20h4M4 20v-4M20 20h-4M20 20v-4M8 12h8",
  watchlist: "M12 5c-5 0-8.5 4.5-9 7 .5 2.5 4 7 9 7s8.5-4.5 9-7c-.5-2.5-4-7-9-7Zm0 10a3 3 0 1 1 0-6 3 3 0 0 1 0 6Z",
  opportunities: "M12 3v3M12 18v3M4.2 4.2l2.1 2.1M17.7 17.7l2.1 2.1M3 12h3M18 12h3M4.2 19.8l2.1-2.1M17.7 6.3l2.1-2.1M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8Z",
  portfolio: "M4 7h16v12H4V7Zm0 0 2-3h12l2 3M9 11h6",
  ai: "M12 2c.7 4 2.6 5.9 6.6 6.6-4 .7-5.9 2.6-6.6 6.6-.7-4-2.6-5.9-6.6-6.6C9.4 7.9 11.3 6 12 2Z",
  news: "M5 4h11a2 2 0 0 1 2 2v14l-3-2-3 2-3-2-3 2V6a2 2 0 0 1 2-2Z",
  reports: "M6 3h8l4 4v14H6V3Zm8 0v4h4M9 12h6M9 15h6M9 9h2",
  strategies: "M4 19V9l6-4 6 4v10M4 19h16M10 19v-6h4v6",
  settings: "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Zm8-3a7.9 7.9 0 0 0-.2-1.8l2-1.6-2-3.4-2.4.9a8 8 0 0 0-3.1-1.8L14 2h-4l-.3 2.3a8 8 0 0 0-3.1 1.8l-2.4-.9-2 3.4 2 1.6A7.9 7.9 0 0 0 4 12c0 .6.1 1.2.2 1.8l-2 1.6 2 3.4 2.4-.9a8 8 0 0 0 3.1 1.8L10 22h4l.3-2.3a8 8 0 0 0 3.1-1.8l2.4.9 2-3.4-2-1.6c.1-.6.2-1.2.2-1.8Z",
  more: "M6 12h.01M12 12h.01M18 12h.01",
};

interface NavIconProps {
  name: string;
  className?: string;
}

export function NavIcon({ name, className }: NavIconProps) {
  const d = PATHS[name] ?? PATHS.more;
  return (
    <svg
      width={20}
      height={20}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
      className={className}
    >
      <path d={d} />
    </svg>
  );
}
