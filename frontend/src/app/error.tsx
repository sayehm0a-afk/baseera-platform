"use client";

import { useEffect } from "react";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-bsr-3 px-bsr-4 text-center">
      <p className="text-lg font-semibold text-bsr-text-primary">
        تعذّر الاتصال بالخادم
      </p>
      <p className="max-w-sm text-sm text-bsr-text-secondary">
        تأكد من أن واجهة برمجة التطبيقات تعمل، ثم حاول مرة أخرى.
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
