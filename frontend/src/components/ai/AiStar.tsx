const SIZES = {
  sm: 12,
  md: 16,
  lg: 20,
} as const;

export type AiStarSize = keyof typeof SIZES;

interface AiStarProps {
  size?: AiStarSize;
  className?: string;
  /** Accessible label; omit (default) to mark the star as purely
   * decorative when it sits next to text that already says "AI". */
  label?: string;
}

/**
 * The Basirah Star -- the AI-attribution mark extracted from the logo
 * glint. Teal-500 only, 12/16/20px only, never on non-AI content
 * (Teal Reservation Rule). This is the single implementation every
 * screen must import; a screen drawing its own star is defective by
 * definition (UI Spec Global Invariants).
 */
export function AiStar({ size = "md", className, label }: AiStarProps) {
  const px = SIZES[size];
  return (
    <svg
      width={px}
      height={px}
      viewBox="0 0 24 24"
      fill="none"
      role={label ? "img" : "presentation"}
      aria-hidden={label ? undefined : true}
      aria-label={label}
      className={className}
    >
      <path
        d="M12 1.5c.8 4.6 2.9 6.7 7.5 7.5-4.6.8-6.7 2.9-7.5 7.5-.8-4.6-2.9-6.7-7.5-7.5 4.6-.8 6.7-2.9 7.5-7.5Z"
        fill="var(--color-bsr-teal-500)"
      />
      <circle cx="19.5" cy="19.5" r="1.5" fill="var(--color-bsr-teal-500)" />
    </svg>
  );
}
