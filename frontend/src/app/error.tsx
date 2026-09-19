"use client";

import { useEffect } from "react";
import * as Sentry from "@sentry/nextjs";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
    // Next.js does not forward errors caught by this client-side error
    // boundary to Sentry's own instrumentation hooks, so it needs an
    // explicit report. This call is a no-op (no network request) when
    // NEXT_PUBLIC_SENTRY_DSN is unset -- see instrumentation-client.ts.
    Sentry.captureException(error);
  }, [error]);

  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-bsr-3 px-bsr-4 text-center">
      <p className="text-lg font-semibold text-bsr-text-primary">
        تعذّر الاتصال بالخادم
      </p>
      <p className="max-w-sm text-sm text-bsr-text-secondary">
        حدث خطأ غير متوقع. حاول مرة أخرى بعد قليل، وإذا استمرت المشكلة تواصل معنا.
      </p>
      <button
        type="button"
        onClick={reset}
        className="rounded-bsr-md bg-bsr-gold-500 px-bsr-4 py-bsr-2 font-semibold text-bsr-navy-950 hover:bg-bsr-gold-400"
      >
        إعادة المحاولة
      </button>
    </div>
  );
}
