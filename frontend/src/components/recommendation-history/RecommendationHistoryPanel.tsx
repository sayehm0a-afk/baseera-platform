"use client";

import { useEffect, useState } from "react";
import { EmptyState } from "@/components/patterns/EmptyState";
import { LoadingScreen } from "@/components/patterns/LoadingScreen";
import { RecommendationBadge, type RecommendationValue } from "@/components/badges/RecommendationBadge";
import { ApiError } from "@/lib/api/client";
import { getRecommendationHistory, getRecommendationHistoryStats } from "@/lib/api/recommendation-history";
import type {
  RecommendationHistoryItem,
  RecommendationHistoryStats,
} from "@/lib/api/recommendation-history-types";

const STATUS_LABELS_AR: Record<string, string> = {
  ACTIVE: "قيد المتابعة",
  COMPLETED: "مكتملة",
  EXPIRED: "منتهية",
  NO_OUTCOMES_TRACKED: "لم يبدأ التتبع بعد",
};

const OUTCOME_STATUS_LABELS_AR: Record<string, string> = {
  PENDING: "قيد الانتظار",
  SUCCESSFUL: "ناجحة",
  FAILED: "فاشلة",
  PARTIAL: "جزئية",
  EXPIRED: "منتهية",
  CANCELLED: "ملغاة",
};

function outcomeColorClass(status: string): string {
  if (status === "SUCCESSFUL") return "text-bsr-action-buy";
  if (status === "FAILED") return "text-bsr-action-sell";
  return "text-bsr-text-secondary";
}

function StatsCard({ stats }: { stats: RecommendationHistoryStats }) {
  return (
    <section className="rounded-bsr-lg border border-bsr-border-subtle bg-bsr-surface-raised p-bsr-4">
      <h2 className="mb-bsr-2 text-base font-semibold text-bsr-text-primary">
        أداء التوصيات — أفق {stats.evaluation_horizon_days} يوم
      </h2>
      {stats.small_sample_warning ? (
        <p className="mb-bsr-2 rounded-bsr-md bg-bsr-action-sell/10 p-bsr-2 text-xs text-bsr-action-sell">
          عيّنة صغيرة ({stats.terminal_sample_size} توصية مكتملة) — هذه النسب قد لا تعكس أداءً موثوقاً بعد.
        </p>
      ) : null}
      <div className="grid grid-cols-2 gap-bsr-2 sm:grid-cols-4">
        <div>
          <p className="text-[11px] text-bsr-text-secondary">حجم العيّنة</p>
          <p className="bsr-numeric text-sm font-semibold text-bsr-text-primary">
            {stats.sample_size} ({stats.terminal_sample_size} مكتملة)
          </p>
        </div>
        <div>
          <p className="text-[11px] text-bsr-text-secondary">نسبة النجاح</p>
          <p className="bsr-numeric text-sm font-semibold text-bsr-text-primary">
            {stats.win_rate !== null ? `${stats.win_rate}%` : "—"}
          </p>
        </div>
        <div>
          <p className="text-[11px] text-bsr-text-secondary">متوسط العائد</p>
          <p className="bsr-numeric text-sm font-semibold text-bsr-text-primary">
            {stats.average_return_pct !== null ? `${stats.average_return_pct}%` : "—"}
          </p>
        </div>
        <div>
          <p className="text-[11px] text-bsr-text-secondary">إصابة الهدف / وقف الخسارة</p>
          <p className="bsr-numeric text-sm font-semibold text-bsr-text-primary">
            {stats.target_hit_rate !== null ? `${stats.target_hit_rate}%` : "—"} /{" "}
            {stats.stop_hit_rate !== null ? `${stats.stop_hit_rate}%` : "—"}
          </p>
        </div>
      </div>
    </section>
  );
}

function HistoryItemRow({ item }: { item: RecommendationHistoryItem }) {
  return (
    <div className="rounded-bsr-md border border-bsr-border-subtle bg-bsr-surface-base p-bsr-3">
      <div className="flex items-center justify-between">
        <div>
          <a
            href={`/stocks/${encodeURIComponent(item.symbol)}`}
            className="text-sm font-semibold text-bsr-text-primary hover:text-bsr-gold-500"
          >
            {item.symbol}
          </a>{" "}
          <span className="text-xs text-bsr-text-secondary">{item.company_name_ar ?? ""}</span>
          <p className="text-[11px] text-bsr-text-tertiary">
            {new Date(item.evaluated_at).toLocaleDateString("ar-SA")} · ثقة {Math.round(item.confidence_score)}%
          </p>
        </div>
        <div className="flex flex-col items-end gap-1">
          <RecommendationBadge value={item.recommendation as RecommendationValue} />
          <span className="text-[11px] text-bsr-text-tertiary">
            {STATUS_LABELS_AR[item.overall_status] ?? item.overall_status}
          </span>
        </div>
      </div>

      {item.outcomes.length > 0 ? (
        <div className="mt-bsr-2 flex flex-wrap gap-bsr-2">
          {item.outcomes.map((outcome) => (
            <span
              key={outcome.evaluation_horizon_days}
              className={`bsr-numeric rounded-bsr-sm bg-bsr-surface-overlay px-bsr-2 py-0.5 text-[11px] ${outcomeColorClass(outcome.status)}`}
            >
              {outcome.evaluation_horizon_days} يوم: {OUTCOME_STATUS_LABELS_AR[outcome.status] ?? outcome.status}
              {outcome.return_pct !== null ? ` (${outcome.return_pct}%)` : ""}
            </span>
          ))}
        </div>
      ) : (
        <p className="mt-bsr-2 text-[11px] text-bsr-text-muted">لا توجد نتائج مسجّلة بعد لهذه التوصية.</p>
      )}
    </div>
  );
}

type LoadState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; items: RecommendationHistoryItem[]; stats: RecommendationHistoryStats };

/** The platform's real, append-only recommendation track record --
 * every item here is a direct read of RecommendationSnapshot/
 * RecommendationOutcome (src.domain.models), including failed and
 * rejected outcomes: this milestone explicitly forbids hiding losses
 * to make the track record look better than it is. `symbol` narrows
 * to one stock's history when provided (the stock-detail view). */
export function RecommendationHistoryPanel({ symbol }: { symbol?: string }) {
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    Promise.all([
      getRecommendationHistory({ symbol, limit: 50 }),
      getRecommendationHistoryStats(7),
    ])
      .then(([history, stats]) => {
        setState({ status: "ready", items: history.items, stats });
      })
      .catch((err) => {
        setState({
          status: "error",
          message: err instanceof ApiError ? err.message : "تعذّر تحميل سجل التوصيات.",
        });
      });
  }, [symbol, reloadToken]);

  if (state.status === "loading") {
    return <LoadingScreen />;
  }
  if (state.status === "error") {
    return (
      <EmptyState
        title="تعذّر تحميل سجل التوصيات"
        description={state.message}
        action={
          <button
            type="button"
            onClick={() => setReloadToken((t) => t + 1)}
            className="rounded-bsr-md border border-bsr-border-subtle bg-bsr-surface-raised px-bsr-3 py-1 text-xs font-semibold text-bsr-text-secondary"
          >
            إعادة المحاولة
          </button>
        }
      />
    );
  }

  return (
    <div className="flex flex-col gap-bsr-4">
      <StatsCard stats={state.stats} />
      {state.items.length === 0 ? (
        <EmptyState
          title="لا يوجد سجل توصيات بعد"
          description={symbol ? "لم تصدر توصية بعد لهذا السهم." : "لم تصدر أي توصية بعد."}
        />
      ) : (
        <div className="flex flex-col gap-bsr-2">
          {state.items.map((item) => (
            <HistoryItemRow key={item.id} item={item} />
          ))}
        </div>
      )}
    </div>
  );
}
