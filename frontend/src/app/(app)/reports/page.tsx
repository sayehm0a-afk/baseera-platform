import { EmptyState } from "@/components/patterns/EmptyState";
import { PortfolioReportLink } from "@/components/reports/PortfolioReportLink";
import { ApiError } from "@/lib/api/client";
import { getRankings } from "@/lib/api/market";
import { RunScanButton } from "@/components/dashboard/RunScanButton";
import type { RankingEntry } from "@/lib/api/types";

async function loadTopSymbols(): Promise<
  { available: true; entries: RankingEntry[] } | { available: false }
> {
  try {
    const result = await getRankings("TOP_BUY");
    return { available: true, entries: result.rankings[0]?.entries.slice(0, 8) ?? [] };
  } catch (error) {
    if (error instanceof ApiError && error.code === "no_market_scan_data") {
      return { available: false };
    }
    throw error;
  }
}

export default async function ReportsPage() {
  const topSymbols = await loadTopSymbols();

  return (
    <div className="flex flex-col gap-bsr-6">
      <h1 className="text-lg font-semibold text-bsr-text-primary">التقارير</h1>

      <section className="rounded-bsr-lg border border-bsr-border-subtle bg-bsr-surface-raised p-bsr-4 md:p-bsr-6">
        <h2 className="mb-bsr-4 text-base font-semibold text-bsr-text-primary">
          تقارير تحليل الأسهم
        </h2>
        {!topSymbols.available ? (
          <EmptyState
            title="لا توجد بيانات مسح للسوق بعد"
            description="شغّل أول مسح ذكي للسوق لعرض تقارير الأسهم الأعلى تقييماً."
            action={<RunScanButton />}
          />
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
