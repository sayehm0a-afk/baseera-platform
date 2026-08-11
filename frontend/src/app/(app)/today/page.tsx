"use client";

import { useCallback, useEffect, useState } from "react";
import { AiStar } from "@/components/ai/AiStar";
import { EmptyState } from "@/components/patterns/EmptyState";
import { LoadingScreen } from "@/components/patterns/LoadingScreen";
import { PersonalOpportunityCard } from "@/components/patterns/PersonalOpportunityCard";
import { getPersonalTopOpportunities } from "@/lib/api/market";
import type { PersonalScanResponse } from "@/lib/api/types";

type TodayData =
  | { status: "loading" }
  | { status: "error" }
  | { status: "ready"; result: PersonalScanResponse };

// Client Component for the same reason every other authenticated
// screen in this app is one (see opportunities/page.tsx): apiFetch
// depends on the browser's httpOnly session cookie.
//
// This is a plain read of GET /api/v1/market/personal/top-opportunities
// -- it never triggers POST /api/v1/market/scan (unlike RunScanButton
// elsewhere in the app). Pressing "امسح السوق الآن" here re-reads the
// latest already-computed scan; it must never cost a fresh SAHMK
// request, however many times the trader presses it in one session.
async function fetchTodayData(): Promise<TodayData> {
  try {
    const result = await getPersonalTopOpportunities();
    return { status: "ready", result };
  } catch {
    return { status: "error" };
  }
}

function useTodayData() {
  const [data, setData] = useState<TodayData>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    fetchTodayData().then((result) => {
      if (!cancelled) setData(result);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const reload = useCallback(() => {
    setData({ status: "loading" });
    fetchTodayData().then(setData);
  }, []);

  return { data, reload };
}

export default function TodayPage() {
  const { data, reload } = useTodayData();

  return (
    <div className="flex flex-col gap-bsr-6">
      <section className="rounded-bsr-lg border border-bsr-border-subtle bg-bsr-surface-raised p-bsr-4 text-center md:p-bsr-6">
        <div className="mb-bsr-2 flex items-center justify-center gap-bsr-2">
          <AiStar />
          <h1 className="text-lg font-semibold text-bsr-text-primary">بصيرة</h1>
        </div>
        <p className="mb-bsr-4 text-sm text-bsr-text-secondary">المحلل الذكي للسوق السعودي</p>
        <button
          type="button"
          onClick={reload}
          disabled={data.status === "loading"}
          className="rounded-bsr-md bg-bsr-gold-500 px-bsr-6 py-bsr-2 font-semibold text-bsr-navy-950 transition-colors hover:bg-bsr-gold-400 disabled:opacity-60"
        >
          {data.status === "loading" ? "جارٍ البحث عن أفضل الفرص..." : "امسح السوق الآن"}
        </button>
      </section>

      {data.status === "loading" ? <LoadingScreen /> : null}

      {data.status === "error" ? (
        <EmptyState
          title="تعذّر تحميل الفرص"
          description="تأكد من اتصال الخادم وحاول مرة أخرى."
          action={
            <button
              type="button"
              onClick={reload}
              className="rounded-bsr-md border border-bsr-border-subtle px-bsr-4 py-bsr-2 text-sm font-semibold text-bsr-text-primary"
            >
              إعادة المحاولة
            </button>
          }
        />
      ) : null}

      {data.status === "ready" && data.result.opportunities.length === 0 ? (
        <EmptyState
          title={data.result.message_ar ?? "لا توجد فرصة عالية الجودة حالياً"}
          description={
            data.result.is_stale
              ? "آخر مسح للسوق قديم جدًا ليُستخدم كتوصية جديدة موثوقة."
              : "تم فحص السوق ولم يجتز أي سهم معايير الجودة اللازمة لترشيحه حاليًا."
          }
        />
      ) : null}

      {data.status === "ready" && data.result.opportunities.length > 0 ? (
        <section className="flex flex-col gap-bsr-4">
          <h2 className="text-base font-semibold text-bsr-text-primary">أفضل فرص المضاربة الآن</h2>
          <div className="grid grid-cols-1 gap-bsr-4 md:grid-cols-2">
            {data.result.opportunities.map((opportunity) => (
              <PersonalOpportunityCard key={opportunity.symbol} opportunity={opportunity} />
            ))}
          </div>
        </section>
      ) : null}
    </div>
  );
}
