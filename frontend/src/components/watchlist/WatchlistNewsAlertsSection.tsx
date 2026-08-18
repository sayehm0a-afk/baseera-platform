"use client";

import { useEffect, useState } from "react";
import { EmptyState } from "@/components/patterns/EmptyState";
import { LoadingScreen } from "@/components/patterns/LoadingScreen";
import { getWatchlistNewsAlerts, refreshWatchlistNewsAlerts } from "@/lib/api/watchlist";
import type { WatchlistNewsAlert } from "@/lib/api/watchlist-types";
import { PORTFOLIO_ALERT_TYPE_LABELS, alertSeverityColorClass } from "@/lib/news-labels";

/** Watchlist-side mirror of PortfolioDetail's NewsAlertsSection
 * (RADAR-C Phase I) -- alerts for watched-but-not-necessarily-owned
 * symbols, sourced from GET/POST /api/v1/watchlist/news-alerts*. Never
 * triggers a live call on mount, only on the explicit "تحديث
 * التنبيهات" action, matching this app's DB-first convention. */
export function WatchlistNewsAlertsSection() {
  const [alerts, setAlerts] = useState<WatchlistNewsAlert[] | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getWatchlistNewsAlerts()
      .then((result) => {
        if (!cancelled) setAlerts(result.alerts);
      })
      .catch(() => {
        if (!cancelled) setError("تعذّر تحميل تنبيهات الأخبار.");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function handleRefresh() {
    setRefreshing(true);
    setError(null);
    try {
      await refreshWatchlistNewsAlerts();
      const result = await getWatchlistNewsAlerts();
      setAlerts(result.alerts);
    } catch {
      setError("تعذّر تحديث تنبيهات الأخبار.");
    } finally {
      setRefreshing(false);
    }
  }

  return (
    <section className="rounded-bsr-lg border border-bsr-border-subtle bg-bsr-surface-raised p-bsr-4">
      <div className="mb-bsr-4 flex items-center justify-between">
        <div>
          <h2 className="text-base font-semibold text-bsr-text-primary">تنبيهات الأخبار</h2>
          <p className="text-sm text-bsr-text-secondary">تنبيهات مبنية على أخبار محللة تخص أسهم قائمة المتابعة.</p>
        </div>
        <button
          type="button"
          onClick={handleRefresh}
          disabled={refreshing}
          className="whitespace-nowrap rounded-bsr-md border border-bsr-border-subtle px-bsr-4 py-bsr-2 text-sm text-bsr-text-primary hover:bg-bsr-surface-overlay disabled:opacity-50"
        >
          {refreshing ? "جارٍ التحديث..." : "تحديث التنبيهات"}
        </button>
      </div>

      {alerts === null && !error ? <LoadingScreen /> : null}

      {error ? <p className="text-sm text-bsr-market-down">{error}</p> : null}

      {alerts !== null && alerts.length === 0 ? (
        <EmptyState title="لا توجد تنبيهات أخبار حالياً لأسهم قائمة المتابعة" />
      ) : null}

      {alerts !== null && alerts.length > 0 ? (
        <ul className="flex flex-col divide-y divide-bsr-border-subtle">
          {alerts.map((alert) => (
            <li key={alert.id} className="flex flex-col gap-bsr-1 py-bsr-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-bsr-2">
                  <span className="bsr-numeric font-semibold text-bsr-text-primary">{alert.symbol}</span>
                  <span
                    className={`rounded-bsr-full px-bsr-3 py-1 text-xs font-medium ${alertSeverityColorClass(alert.severity)}`}
                  >
                    {PORTFOLIO_ALERT_TYPE_LABELS[alert.alert_type] ?? alert.alert_type}
                  </span>
                </div>
                <span className="text-xs text-bsr-text-muted">
                  {new Date(alert.generated_at).toLocaleString("ar-SA")}
                </span>
              </div>
              <p className="text-sm text-bsr-text-secondary">{alert.message}</p>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
