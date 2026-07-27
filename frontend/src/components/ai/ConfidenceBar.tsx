interface ConfidenceBarProps {
  /** 0-100 */
  confidence: number;
  className?: string;
}

/**
 * AI confidence fill bar -- teal only (Teal Reservation Rule: AI
 * confidence is explicitly AI-attributed content). Fills over the
 * confidence-fill motion (400ms).
 */
export function ConfidenceBar({ confidence, className }: ConfidenceBarProps) {
  const clamped = Math.max(0, Math.min(100, confidence));
  return (
    <div
      className={`h-1.5 w-full overflow-hidden rounded-bsr-full bg-bsr-navy-700 ${className ?? ""}`}
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(clamped)}
    >
      <div
        className="h-full rounded-bsr-full bg-bsr-teal-500 transition-[width] duration-[var(--duration-bsr-confidence-fill)] ease-out"
        style={{ width: `${clamped}%` }}
      />
    </div>
  );
}
