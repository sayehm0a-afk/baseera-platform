import { AiStar } from "@/components/ai/AiStar";

/** The one shared full-screen loading state. Uses the AI pulse motion
 * (1s loop) -- one of exactly 5 AI motions system-wide -- rather than
 * an invented spinner. */
export function LoadingScreen() {
  return (
    <div className="flex h-full min-h-[50vh] w-full flex-1 flex-col items-center justify-center gap-bsr-3">
      <AiStar size="lg" className="animate-[bsr-pulse_1s_ease-in-out_infinite]" />
      <p className="text-sm text-bsr-text-secondary">جارٍ التحميل...</p>
    </div>
  );
}
