"use client";

import Link from "next/link";
import { useState } from "react";
import type { PortfolioHoldingDetail } from "@/lib/api/portfolio-types";
import { HolderGuidanceBadge } from "./HolderGuidanceBadge";

function fmt(value: number | null): string {
  return value == null ? "—" : value.toFixed(2);
}

function fmtPct(value: number | null): string {
  if (value == null) return "—";
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

/** RADAR-C Phase H: one real, persisted holding -- quantity/average
 * cost/current price/invested cost/current value/unrealized P&L are
 * all either verbatim backend fields or "—" (never fabricated) when
 * the backend had no persisted price to compute from. Editing swaps
 * to an inline quantity/average-cost form; deleting asks for
 * confirmation once, inline, rather than a browser confirm() dialog. */
export function HoldingRow({
  holding,
  onUpdate,
  onDelete,
}: {
  holding: PortfolioHoldingDetail;
  onUpdate: (quantity: number, averageCost: number | undefined) => Promise<void>;
  onDelete: () => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [quantity, setQuantity] = useState(String(holding.quantity));
  const [averageCost, setAverageCost] = useState(
    holding.average_cost != null ? String(holding.average_cost) : ""
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const pnlColorClass =
    holding.unrealized_pnl == null
      ? "text-bsr-text-secondary"
      : holding.unrealized_pnl > 0
        ? "text-bsr-market-up"
        : holding.unrealized_pnl < 0
          ? "text-bsr-market-down"
          : "text-bsr-text-secondary";

  async function handleSave() {
    setError(null);
    const parsedQuantity = Number(quantity);
    if (!(parsedQuantity > 0)) {
      setError("الكمية يجب أن تكون أكبر من صفر.");
      return;
    }
    setSaving(true);
    try {
      await onUpdate(parsedQuantity, averageCost.trim() ? Number(averageCost) : undefined);
      setEditing(false);
    } catch {
      setError("تعذّر حفظ التعديل. حاول مرة أخرى.");
    } finally {
      setSaving(false);
    }
  }

  if (editing) {
    return (
      <div className="flex flex-col gap-bsr-2 rounded-bsr-md border border-bsr-border-subtle bg-bsr-surface-raised p-bsr-3">
        <span className="text-sm font-semibold text-bsr-text-primary">
          {holding.name_ar ?? holding.name_en} ({holding.symbol})
        </span>
        <div className="grid grid-cols-2 gap-bsr-2 sm:grid-cols-4">
          <input
            type="number"
            min={0}
            step="1"
            value={quantity}
            onChange={(e) => setQuantity(e.target.value)}
            placeholder="الكمية"
            className="bsr-numeric rounded-bsr-md border border-bsr-border-subtle bg-bsr-surface-base px-bsr-2 py-bsr-1.5 text-sm text-bsr-text-primary focus:border-bsr-gold-500 focus:outline-none"
          />
          <input
            type="number"
            min={0}
            step="0.01"
            value={averageCost}
            onChange={(e) => setAverageCost(e.target.value)}
            placeholder="متوسط التكلفة"
            className="bsr-numeric rounded-bsr-md border border-bsr-border-subtle bg-bsr-surface-base px-bsr-2 py-bsr-1.5 text-sm text-bsr-text-primary focus:border-bsr-gold-500 focus:outline-none"
          />
          <button
            type="button"
            onClick={handleSave}
            disabled={saving}
            className="rounded-bsr-md bg-bsr-gold-500 px-bsr-3 py-bsr-1.5 text-sm font-semibold text-bsr-navy-950 hover:bg-bsr-gold-400 disabled:opacity-60"
          >
            {saving ? "جارٍ الحفظ..." : "حفظ"}
          </button>
          <button
            type="button"
            onClick={() => setEditing(false)}
            className="rounded-bsr-md border border-bsr-border-subtle px-bsr-3 py-bsr-1.5 text-sm text-bsr-text-secondary hover:bg-bsr-surface-overlay"
          >
            إلغاء
          </button>
        </div>
        {error ? <p className="text-xs text-bsr-market-down">{error}</p> : null}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-bsr-2 rounded-bsr-md border border-bsr-border-subtle bg-bsr-surface-raised p-bsr-3">
      <div className="flex flex-wrap items-start justify-between gap-bsr-2">
        <Link href={`/stocks/${encodeURIComponent(holding.symbol)}`} className="min-w-0">
          <span className="block truncate text-sm font-semibold text-bsr-text-primary hover:text-bsr-gold-500">
            {holding.name_ar ?? holding.name_en}
          </span>
          <span className="bsr-numeric text-xs text-bsr-text-secondary">
            {holding.symbol}
            {holding.sector_ar ? ` · ${holding.sector_ar}` : ""}
          </span>
        </Link>
        {holding.guidance_decision && holding.guidance_label_ar ? (
          <HolderGuidanceBadge value={holding.guidance_decision} labelAr={holding.guidance_label_ar} />
        ) : (
          <span className="rounded-bsr-full bg-bsr-surface-overlay px-bsr-3 py-bsr-1 text-xs text-bsr-text-secondary">
            بلا توصية بعد
          </span>
        )}
      </div>

      <div className="grid grid-cols-2 gap-bsr-2 sm:grid-cols-4">
        <div>
          <p className="text-[11px] text-bsr-text-secondary">الكمية × التكلفة</p>
          <p className="bsr-numeric text-sm text-bsr-text-primary">
            {holding.quantity} × {fmt(holding.average_cost)}
          </p>
        </div>
        <div>
          <p className="text-[11px] text-bsr-text-secondary">السعر الحالي</p>
          <p className="bsr-numeric text-sm text-bsr-text-primary">
            {fmt(holding.current_price)}
          </p>
          <p className="text-[10px] text-bsr-text-muted">{holding.freshness_label_ar}</p>
        </div>
        <div>
          <p className="text-[11px] text-bsr-text-secondary">القيمة الحالية</p>
          <p className="bsr-numeric text-sm text-bsr-text-primary">{fmt(holding.current_value)}</p>
        </div>
        <div>
          <p className="text-[11px] text-bsr-text-secondary">الربح/الخسارة غير المحقق</p>
          <p className={`bsr-numeric text-sm font-semibold ${pnlColorClass}`}>
            {fmt(holding.unrealized_pnl)} ({fmtPct(holding.unrealized_pnl_pct)})
          </p>
        </div>
      </div>

      {holding.guidance_basis_ar ? (
        <p className="text-xs text-bsr-text-secondary">{holding.guidance_basis_ar}</p>
      ) : null}

      <div className="flex items-center gap-bsr-2">
        <button
          type="button"
          onClick={() => setEditing(true)}
          className="rounded-bsr-md border border-bsr-border-subtle px-bsr-3 py-bsr-1 text-xs font-semibold text-bsr-text-secondary hover:bg-bsr-surface-overlay"
        >
          تعديل
        </button>
        {confirmingDelete ? (
          <>
            <span className="text-xs text-bsr-text-secondary">تأكيد الحذف؟</span>
            <button
              type="button"
              onClick={onDelete}
              className="rounded-bsr-md bg-bsr-action-sell/15 px-bsr-3 py-bsr-1 text-xs font-semibold text-bsr-action-sell hover:bg-bsr-action-sell/25"
            >
              نعم، احذف
            </button>
            <button
              type="button"
              onClick={() => setConfirmingDelete(false)}
              className="rounded-bsr-md px-bsr-3 py-bsr-1 text-xs text-bsr-text-secondary hover:bg-bsr-surface-overlay"
            >
              تراجع
            </button>
          </>
        ) : (
          <button
            type="button"
            onClick={() => setConfirmingDelete(true)}
            className="rounded-bsr-md px-bsr-3 py-bsr-1 text-xs font-semibold text-bsr-text-secondary hover:bg-bsr-action-sell/15 hover:text-bsr-action-sell"
          >
            حذف
          </button>
        )}
      </div>
    </div>
  );
}
