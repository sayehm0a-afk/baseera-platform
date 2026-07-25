"use client";

interface AiSweepProps {
  /** Change this key to replay the sweep for a new AI event (e.g. a
   * fresh recommendation arriving); omitting it plays the sweep once
   * on mount only. Never loops -- the Sweep is a one-shot signature
   * motion, at most once per module per event (DS §20). Passed
   * straight through as the element's React key so a change remounts
   * (and thus replays) the CSS animation without any internal state. */
  eventKey?: string | number;
}

/**
 * The Basirah Sweep -- 700ms teal radial arc, the system's signature
 * AI motion. Absolute-positioned overlay; wrap the module it should
 * play across with `position: relative`.
 */
export function AiSweep({ eventKey }: AiSweepProps) {
  return (
    <span
      key={eventKey ?? "initial"}
      aria-hidden
      className="bsr-ai-sweep pointer-events-none absolute inset-0 overflow-hidden rounded-[inherit]"
    />
  );
}
