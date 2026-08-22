"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AiStar } from "@/components/ai/AiStar";
import { EmptyState } from "@/components/patterns/EmptyState";
import { LoadingScreen } from "@/components/patterns/LoadingScreen";
import { getMyWatchlist, removeFromWatchlist } from "@/lib/api/watchlist";
import type { WatchlistItem } from "@/lib/api/watchlist-types";
import { formatArabicDateTime, formatRelativeAgeAr, freshnessLabelAr } from "@/lib/format/freshness";

type PanelState =
  | { status: "loading" }
  | { status: "error" }
  | { status: "ready"; items: WatchlistItem[] };

function formatPrice(value: number | null): string {
  return value == null ? "--" : value.toLocaleString("ar-SA", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

/** The authenticated user's own saved symbols -- real data only, never
 * a fabricated example. Add/remove happen elsewhere (the stock page's
 * AddToWatchlistButton); this panel is read + remove. */
export function MyWatchlistPanel() {
  const [state, setState] = useState<PanelState>({ status: "loading" });
  const [removingSymbol, setRemovingSymbol] = useState<string | null>(null);
  // Bumped to re-trigger the fetch effect below (e.g. after a failed
  // remove, to re-sync with the server's real state) -- matches
  // useCategoryFetch's own "only setState inside .then/.catch, never
  // synchronously in the effect body" discipline.
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let cancelled = false;
    getMyWatchlist()
      .then((result) => {
        if (!cancelled) setState({ status: "ready", items: result.items });
      })
      .catch(() => {
        if (!cancelled) setState({ status: "error" });
      });
    return () => {
      cancelled = true;
    };
  }, [reloadToken]);

  async function handleRemove(symbol: string) {
    setRemovingSymbol(symbol);
    try {
      await removeFromWatchlist(symbol);
      setState((prev) =>
        prev.status === "ready" ? { status: "ready", items: prev.items.filter((item) => item.symbol !== symbol) } : prev
      );
    } catch {
      // Re-sync with the server's real state rather than guessing what went wrong.
      setReloadToken((token) => token + 1);
    } finally {
      setRemovingSymbol(null);
    }
  }

  if (state.status === "loading") {
    return <LoadingScreen />;
  }

  if (state.status === "error") {
    return <EmptyState title="تعذّر تحميل قائمة المتابعة" description="تأكد من اتصال الخادم وحاول مرة أخرى." />;
  }

  if (state.items.length === 0) {
    return (
      <EmptyState
        title="قائمة المتابعة فارغة"
        description="أضف الأسهم التي تهمك من صفحة السهم لمتابعة توصياتها وأسعارها هنا."
      />
    );
  }

  return (
    <ul className="flex flex-col divide-y divide-bsr-border-subtle">
      {state.items.map((item) => (
        <li key={item.symbol} className="flex flex-col gap-bsr-2 px-bsr-4 py-bsr-3">
          <div className="flex items-center justify-between gap-bsr-3">
            <Link href={`/stocks/${item.symbol}`} className="flex flex-col">
              <span className="bsr-numeric font-semibold text-bsr-text-primary">{item.symbol}</span>
              {item.company_name_ar ? (
                <span className="text-sm text-bsr-text-secondary">{item.company_name_ar}</span>
              ) : null}
            </Link>
            <button
              type="button"
              onClick={() => handleRemove(item.symbol)}
              disabled={removingSymbol === item.symbol}
              className="text-sm text-bsr-action-sell disabled:opacity-50"
            >
              {removingSymbol === item.symbol ? "جارٍ الإزالة..." : "إزالة"}
            </button>
          </div>

          {item.latest_decision_label_ar ? (
            <div className="flex flex-wrap items-center gap-bsr-3 text-sm">
              <span className="rounded-bsr-full bg-bsr-surface-overlay px-bsr-3 py-1 font-medium text-bsr-text-primary">
                {item.latest_decision_label_ar}
              </span>
              {item.latest_confidence_score != null ? (
                <span className="bsr-numeric text-bsr-teal-500">ثقة {Math.round(item.latest_confidence_score)}%</span>
              ) : null}
              {item.latest_current_price != null ? (
                <span className="bsr-numeric text-bsr-text-secondary">السعر الحالي: {formatPrice(item.latest_current_price)}</span>
              ) : null}
            </div>
          ) : (
            <p className="text-sm text-bsr-text-secondary">لم يتم تحليل هذا السهم بعد.</p>
          )}

          {item.latest_decision_label_ar && item.latest_decision_timestamp ? (
            <p className="text-xs text-bsr-text-secondary">
              {freshnessLabelAr(item.latest_data_freshness_status)} · آخر تحديث:{" "}
              <span className="bsr-numeric">{formatArabicDateTime(item.latest_decision_timestamp)}</span> (
              {formatRelativeAgeAr(item.latest_decision_timestamp)})
            </p>
          ) : null}

          {item.radar_is_live_opportunity ? (
            <div className="flex items-center gap-bsr-2 text-xs text-bsr-teal-500">
              <AiStar size="sm" />
              <span>
                فرصة حية في الرادار الذكي
                {item.radar_stage1_rank != null ? ` · الترتيب #${item.radar_stage1_rank}` : ""}
              </span>
            </div>
          ) : null}
          {item.radar_is_live_opportunity && item.radar_ranking_reason_ar ? (
            <p className="text-xs text-bsr-text-secondary">{item.radar_ranking_reason_ar}</p>
          ) : null}

          {(item.latest_target_1 != null || item.latest_stop_loss != null) && item.latest_decision_timestamp != null ? (
            <div className="flex flex-wrap gap-bsr-4 text-xs text-bsr-text-secondary">
              {item.latest_target_1 != null ? (
                <span>
                  الهدف الأول: <span className="bsr-numeric">{formatPrice(item.latest_target_1)}</span>
                </span>
              ) : null}
              {item.latest_stop_loss != null ? (
                <span>
                  وقف الخسارة: <span className="bsr-numeric">{formatPrice(item.latest_stop_loss)}</span>
                </span>
              ) : null}
            </div>
          ) : null}
        </li>
      ))}
    </ul>
  );
}
