import { AiStar } from "@/components/ai/AiStar";

/** The one shared top app bar every authenticated screen reuses
 * (UI Spec Global Invariants §0). */
export function TopBar() {
  return (
    <header className="flex h-16 shrink-0 items-center gap-bsr-4 border-b border-bsr-border-subtle bg-bsr-surface-base px-bsr-4 md:px-bsr-6">
      <div className="flex items-center gap-bsr-2">
        <AiStar size="lg" label="بصيرة" />
        <span className="text-lg font-semibold text-bsr-white">بصيرة</span>
        <span className="text-lg font-semibold text-bsr-teal-500">AI</span>
      </div>

      <div className="hidden flex-1 items-center md:flex">
        <label className="relative w-full max-w-md">
          <span className="sr-only">ابحث عن سهم أو مؤشر</span>
          <input
            type="search"
            placeholder="ابحث عن سهم أو مؤشر..."
            className="w-full rounded-bsr-full border border-bsr-border-subtle bg-bsr-surface-raised px-bsr-4 py-bsr-2 text-sm text-bsr-text-primary placeholder:text-bsr-text-muted focus:border-bsr-gold-500 focus:outline-none"
          />
        </label>
      </div>

      <div className="ms-auto flex items-center gap-bsr-3">
        <button
          type="button"
          aria-label="التنبيهات"
          className="flex h-9 w-9 items-center justify-center rounded-bsr-full text-bsr-text-secondary hover:bg-bsr-surface-raised"
        >
          <svg width={18} height={18} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75} aria-hidden>
            <path d="M18 16v-5a6 6 0 1 0-12 0v5l-2 2v1h16v-1l-2-2Z" strokeLinecap="round" strokeLinejoin="round" />
            <path d="M10 21a2 2 0 0 0 4 0" strokeLinecap="round" />
          </svg>
        </button>
        <button
          type="button"
          aria-label="الملف الشخصي"
          className="flex h-9 w-9 items-center justify-center rounded-bsr-full bg-bsr-surface-raised text-sm font-semibold text-bsr-text-primary"
        >
          م
        </button>
      </div>
    </header>
  );
}
