"use client";

import { EmptyState } from "@/components/patterns/EmptyState";
import { LoadingScreen } from "@/components/patterns/LoadingScreen";
import { PortfolioReportLink } from "@/components/reports/PortfolioReportLink";
import { RecommendationHistoryPanel } from "@/components/recommendation-history/RecommendationHistoryPanel";
import { getRankings } from "@/lib/api/market";
import { RunScanButton } from "@/components/dashboard/RunScanButton";
import { useCategoryFetch } from "@/lib/hooks/useCategoryFetch";
import type { RankingEntry } from "@/lib/api/types";

// Client Component: same reason as /opportunities and /dashboard --
// apiFetch depends on the browser's httpOnly session cookie, which a
// Next.js Server Component fetch never receives. This page was
// previously an async Server Component that called getRankings()
// server-side; confirmed in production (2026-08-06) that every real
// login crashed it with "An error occurred in the Server Components
// render" because the server-side request had no session cookie to
// send, got a 401 back, and loadTopSymbols() only caught the
// no_market_scan_data error code -- any other error (including this
// one) was re-thrown, crashing the whole page.
async function loadTopSymbols(category: string): Promise<RankingEntry[]> {
  const result = await getRankings(category);
  return result.rankings[0]?.entries.slice(0, 8) ?? [];
}

export default function ReportsPage() {
  const topSymbols = useCategoryFetch("TOP_BUY", loadTopSymbols);

  return (
    <div className="flex flex-col gap-bsr-6">
      <h1 className="text-lg font-semibold text-bsr-text-primary">التقارير</h1>

      <section className="rounded-bsr-lg border border-bsr-border-subtle bg-bsr-surface-raised p-bsr-4 md:p-bsr-6">
        <h2 className="mb-bsr-4 text-base font-semibold text-bsr-text-primary">
          تقارير تحليل الأسهم
        </h2>
        {topSymbols.status === "loading" ? (
          <LoadingScreen />
        ) : topSymbols.status === "unavailable" ? (
          <EmptyState
            title="لا توجد بيانات مسح للسوق بعد"
            description="شغّل أول مسح ذكي للسوق لعرض تقارير الأسهم الأعلى تقييماً."
            action={<RunScanButton />}
          />
        ) : topSymbols.status === "error" ? (
          <EmptyState title="تعذّر تحميل الأسهم المرشحة" description="حاول تحديث الصفحة." />
        ) : topSymbols.entries.length === 0 ? (
          <EmptyState title="لا توجد أسهم مرشحة حالياً" />
        ) : (
          <div className="grid grid-cols-2 gap-bsr-2 sm:grid-cols-4">
            {topSymbols.entries.map((entry) => (
              <a
                key={entry.symbol}
                href={`/stocks/${encodeURIComponent(entry.symbol)}`}
                className="bsr-numeric rounded-bsr-md border border-bsr-border-subtle bg-bsr-surface-overlay px-bsr-3 py-bsr-2 text-center text-bsr-text-primary hover:border-bsr-gold-500/40"
              >
                {entry.symbol}
              </a>
            ))}
          </div>
        )}
        <p className="mt-bsr-3 text-xs text-bsr-text-muted">
          أو ابحث عن أي رمز من صفحة{" "}
          <a href="/ai" className="text-bsr-gold-500 hover:underline">
            الذكاء الاصطناعي
          </a>{" "}
          للحصول على تقريره الكامل.
        </p>
      </section>

      <section className="rounded-bsr-lg border border-bsr-border-subtle bg-bsr-surface-raised p-bsr-4 md:p-bsr-6">
        <h2 className="mb-bsr-4 text-base font-semibold text-bsr-text-primary">تقرير المحفظة</h2>
        <PortfolioReportLink />
      </section>

      <section className="rounded-bsr-lg border border-bsr-border-subtle bg-bsr-surface-raised p-bsr-4 md:p-bsr-6">
        <h2 className="mb-bsr-4 text-base font-semibold text-bsr-text-primary">سجل التوصيات</h2>
        <p className="mb-bsr-4 text-xs text-bsr-text-secondary">
          السجل الحقيقي الكامل لكل توصية أصدرتها المنصة ونتيجتها الفعلية — بما في ذلك التوصيات غير الموفقة، لا يتم
          إخفاء أي نتيجة.
        </p>
        <RecommendationHistoryPanel />
      </section>

      <section className="rounded-bsr-lg border border-bsr-border-subtle bg-bsr-surface-raised p-bsr-4 md:p-bsr-6">
        <h2 className="mb-bsr-4 text-base font-semibold text-bsr-text-primary">
          التقارير الدورية
        </h2>
        <EmptyState
          title="التقارير الدورية قيد الربط بالخادم"
          description="التقرير اليومي، تقرير القطاعات، والتقارير الشهرية والربعية بصيغة PDF ستتوفر بمجرد ربط خدمة توليد التقارير في الخادم."
        />
      </section>
    </div>
  );
}
