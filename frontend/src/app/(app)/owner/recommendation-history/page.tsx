"use client";

import { useEffect, useState } from "react";
import { RequireStaff } from "@/components/auth/RequireStaff";
import { OwnerNav } from "@/components/owner/OwnerNav";
import { RecommendationBadge, type RecommendationValue } from "@/components/badges/RecommendationBadge";
import { EmptyState } from "@/components/patterns/EmptyState";
import { LoadingScreen } from "@/components/patterns/LoadingScreen";
import { ApiError } from "@/lib/api/client";
import { getAdminRecommendationHistory } from "@/lib/api/recommendation-history";
import type { RecommendationHistoryAuditItem } from "@/lib/api/recommendation-history-types";

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-bsr-lg border border-bsr-border-subtle bg-bsr-surface-raised p-bsr-4">
      <h2 className="mb-bsr-2 text-base font-semibold text-bsr-text-primary">{title}</h2>
      {children}
    </section>
  );
}

function AuditItemDetail({ item }: { item: RecommendationHistoryAuditItem }) {
  return (
    <div className="flex flex-col gap-bsr-3">
      <div className="grid grid-cols-2 gap-bsr-2 sm:grid-cols-4">
        <div>
          <p className="text-[11px] text-bsr-text-secondary">إصدار المحرك</p>
          <p className="text-sm font-semibold text-bsr-text-primary">{item.engine_version}</p>
        </div>
        <div>
          <p className="text-[11px] text-bsr-text-secondary">إصدار المعايرة</p>
          <p className="text-sm font-semibold text-bsr-text-primary">{item.calibration_version ?? "—"}</p>
        </div>
        <div>
          <p className="text-[11px] text-bsr-text-secondary">المصدر</p>
          <p className="text-sm font-semibold text-bsr-text-primary">{item.source ?? "—"}</p>
        </div>
        <div>
          <p className="text-[11px] text-bsr-text-secondary">إجمالي النقاط</p>
          <p className="bsr-numeric text-sm font-semibold text-bsr-text-primary">{item.total_score ?? "—"}</p>
        </div>
      </div>

      {item.contributor_breakdown ? (
        <div>
          <p className="mb-bsr-1 text-xs font-semibold text-bsr-text-primary">تفصيل المساهمين</p>
          <pre className="max-h-64 overflow-auto rounded-bsr-md bg-bsr-surface-base p-bsr-2 text-[11px] text-bsr-text-secondary">
            {JSON.stringify(item.contributor_breakdown, null, 2)}
          </pre>
        </div>
      ) : null}

      {item.signals ? (
        <div>
          <p className="mb-bsr-1 text-xs font-semibold text-bsr-text-primary">الإشارات الخام</p>
          <pre className="max-h-64 overflow-auto rounded-bsr-md bg-bsr-surface-base p-bsr-2 text-[11px] text-bsr-text-secondary">
            {JSON.stringify(item.signals, null, 2)}
          </pre>
        </div>
      ) : null}
    </div>
  );
}

function RecommendationHistoryAuditPageInner() {
  const [items, setItems] = useState<RecommendationHistoryAuditItem[] | null>(null);
  const [symbolFilter, setSymbolFilter] = useState("");
  const [selected, setSelected] = useState<RecommendationHistoryAuditItem | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  function refresh(symbol?: string) {
    setLoading(true);
    getAdminRecommendationHistory({ symbol: symbol || undefined, limit: 50 })
      .then((data) => setItems(data.items))
      .catch((err) => setError(err instanceof ApiError ? err.message : "تعذّر تحميل سجل التوصيات."))
      .finally(() => setLoading(false));
  }

  // Initial load -- `loading` already defaults to true via useState above,
  // so this effect never needs a synchronous setState call of its own
  // (react-hooks/set-state-in-effect forbids that); every setState here
  // happens strictly inside a promise callback.
  useEffect(() => {
    getAdminRecommendationHistory({ limit: 50 })
      .then((data) => setItems(data.items))
      .catch((err) => setError(err instanceof ApiError ? err.message : "تعذّر تحميل سجل التوصيات."))
      .finally(() => setLoading(false));
  }, []);

  if (loading && items === null) {
    return (
      <div className="flex flex-col gap-bsr-4">
        <OwnerNav />
        <LoadingScreen />
      </div>
    );
  }
  if (error) {
    return (
      <div className="flex flex-col gap-bsr-4">
        <OwnerNav />
        <EmptyState title="تعذّر تحميل سجل التوصيات" description={error} />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-bsr-4">
      <OwnerNav />
      <h1 className="text-lg font-semibold text-bsr-text-primary">سجل التوصيات — تدقيق داخلي</h1>
      <p className="text-sm text-bsr-text-secondary">
        نفس سجل التوصيات الحقيقي المعروض للمستخدمين، مع الحقول الداخلية الإضافية (تفصيل المساهمين، الإشارات الخام،
        إصدار المعايرة) اللازمة لتدقيق سبب كل توصية.
      </p>

      <Card title="تصفية">
        <div className="flex gap-bsr-2">
          <input
            type="text"
            value={symbolFilter}
            onChange={(e) => setSymbolFilter(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && refresh(symbolFilter)}
            placeholder="تصفية حسب رمز السهم"
            className="rounded-bsr-md border border-bsr-border-subtle bg-bsr-surface-base px-bsr-2 py-1 text-sm text-bsr-text-primary"
          />
          <button
            type="button"
            onClick={() => refresh(symbolFilter)}
            className="rounded-bsr-md border border-bsr-border-subtle bg-bsr-surface-raised px-bsr-3 py-1 text-xs font-semibold text-bsr-text-secondary"
          >
            بحث
          </button>
        </div>
      </Card>

      <Card title={`السجل (${items?.length ?? 0})`}>
        {items === null || items.length === 0 ? (
          <p className="text-sm text-bsr-text-muted">لا توجد توصيات مسجّلة بعد.</p>
        ) : (
          <div className="flex flex-col gap-bsr-1">
            {items.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => setSelected(selected?.id === item.id ? null : item)}
                className={`flex items-center justify-between rounded-bsr-md border p-bsr-2 text-start ${
                  selected?.id === item.id
                    ? "border-bsr-gold-500 bg-bsr-surface-overlay"
                    : "border-bsr-border-subtle bg-bsr-surface-base"
                }`}
              >
                <div>
                  <span className="text-sm font-semibold text-bsr-text-primary">{item.symbol}</span>{" "}
                  <span className="text-xs text-bsr-text-secondary">{item.company_name_ar ?? ""}</span>
                  <p className="text-[11px] text-bsr-text-tertiary">
                    {new Date(item.evaluated_at).toLocaleString("ar-SA")}
                  </p>
                </div>
                <RecommendationBadge value={item.recommendation as RecommendationValue} />
              </button>
            ))}
          </div>
        )}
      </Card>

      {selected ? (
        <Card title={`تفاصيل التدقيق — ${selected.symbol}`}>
          <AuditItemDetail item={selected} />
        </Card>
      ) : null}
    </div>
  );
}

export default function RecommendationHistoryAuditPage() {
  return (
    <RequireStaff>
      <RecommendationHistoryAuditPageInner />
    </RequireStaff>
  );
}
