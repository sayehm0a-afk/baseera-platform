"use client";

import { useState } from "react";
import { analyzePortfolio } from "@/lib/api/portfolio";
import type { PortfolioAnalysis } from "@/lib/api/portfolio-types";

interface HoldingRow {
  symbol: string;
  quantity: string;
  averageCost: string;
}

const EMPTY_ROW: HoldingRow = { symbol: "", quantity: "", averageCost: "" };

interface PortfolioFormProps {
  portfolioId?: number;
  initialName?: string;
  initialCash?: number;
  initialHoldings?: { symbol: string; quantity: number; averageCost: number | null }[];
  onAnalyzed: (analysis: PortfolioAnalysis) => void;
}

export function PortfolioForm({
  portfolioId,
  initialName,
  initialCash,
  initialHoldings,
  onAnalyzed,
}: PortfolioFormProps) {
  const [name, setName] = useState(initialName ?? "محفظتي");
  const [cash, setCash] = useState(String(initialCash ?? 0));
  const [rows, setRows] = useState<HoldingRow[]>(
    initialHoldings && initialHoldings.length > 0
      ? initialHoldings.map((h) => ({
          symbol: h.symbol,
          quantity: String(h.quantity),
          averageCost: h.averageCost != null ? String(h.averageCost) : "",
        }))
      : [{ ...EMPTY_ROW }]
  );
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function updateRow(index: number, patch: Partial<HoldingRow>) {
    setRows((prev) => prev.map((row, i) => (i === index ? { ...row, ...patch } : row)));
  }

  function addRow() {
    setRows((prev) => [...prev, { ...EMPTY_ROW }]);
  }

  function removeRow(index: number) {
    setRows((prev) => prev.filter((_, i) => i !== index));
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    const holdings = rows
      .filter((row) => row.symbol.trim() && row.quantity.trim())
      .map((row) => ({
        symbol: row.symbol.trim(),
        quantity: Number(row.quantity),
        average_cost: row.averageCost.trim() ? Number(row.averageCost) : undefined,
      }));

    if (holdings.length === 0) {
      setError("أضف مركزاً واحداً على الأقل (رمز السهم والكمية).");
      return;
    }

    setSubmitting(true);
    try {
      const analysis = await analyzePortfolio({
        portfolio_id: portfolioId,
        name: name.trim() || "محفظتي",
        holdings,
        cash: Number(cash) || 0,
      });
      onAnalyzed(analysis);
    } catch {
      setError("تعذّر تحليل المحفظة. تحقق من رموز الأسهم وحاول مرة أخرى.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="flex flex-col gap-bsr-4 rounded-bsr-lg border border-bsr-border-subtle bg-bsr-surface-raised p-bsr-4 md:p-bsr-6"
    >
      <div className="grid grid-cols-1 gap-bsr-4 sm:grid-cols-2">
        <label className="flex flex-col gap-bsr-1">
          <span className="text-sm text-bsr-text-secondary">اسم المحفظة</span>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="rounded-bsr-md border border-bsr-border-subtle bg-bsr-surface-base px-bsr-3 py-bsr-2 text-bsr-text-primary focus:border-bsr-gold-500 focus:outline-none"
          />
        </label>
        <label className="flex flex-col gap-bsr-1">
          <span className="text-sm text-bsr-text-secondary">الرصيد النقدي</span>
          <input
            type="number"
            min={0}
            step="0.01"
            value={cash}
            onChange={(e) => setCash(e.target.value)}
            className="bsr-numeric rounded-bsr-md border border-bsr-border-subtle bg-bsr-surface-base px-bsr-3 py-bsr-2 text-bsr-text-primary focus:border-bsr-gold-500 focus:outline-none"
          />
        </label>
      </div>

      <div className="flex flex-col gap-bsr-2">
        <span className="text-sm text-bsr-text-secondary">المراكز</span>
        {rows.map((row, index) => (
          <div key={index} className="grid grid-cols-[1fr_1fr_1fr_auto] items-center gap-bsr-2">
            <input
              placeholder="الرمز (مثال: 2222)"
              value={row.symbol}
              onChange={(e) => updateRow(index, { symbol: e.target.value })}
              className="bsr-numeric rounded-bsr-md border border-bsr-border-subtle bg-bsr-surface-base px-bsr-3 py-bsr-2 text-bsr-text-primary focus:border-bsr-gold-500 focus:outline-none"
            />
            <input
              type="number"
              min={0}
              step="1"
              placeholder="الكمية"
              value={row.quantity}
              onChange={(e) => updateRow(index, { quantity: e.target.value })}
              className="bsr-numeric rounded-bsr-md border border-bsr-border-subtle bg-bsr-surface-base px-bsr-3 py-bsr-2 text-bsr-text-primary focus:border-bsr-gold-500 focus:outline-none"
            />
            <input
              type="number"
              min={0}
              step="0.01"
              placeholder="متوسط التكلفة (اختياري)"
              value={row.averageCost}
              onChange={(e) => updateRow(index, { averageCost: e.target.value })}
              className="bsr-numeric rounded-bsr-md border border-bsr-border-subtle bg-bsr-surface-base px-bsr-3 py-bsr-2 text-bsr-text-primary focus:border-bsr-gold-500 focus:outline-none"
            />
            <button
              type="button"
              onClick={() => removeRow(index)}
              aria-label="إزالة"
              className="flex h-9 w-9 items-center justify-center rounded-bsr-md text-bsr-text-secondary hover:bg-bsr-surface-overlay hover:text-bsr-action-sell"
            >
              ×
            </button>
          </div>
        ))}
        <button
          type="button"
          onClick={addRow}
          className="self-start rounded-bsr-md px-bsr-3 py-bsr-1 text-sm text-bsr-gold-500 hover:bg-bsr-surface-overlay"
        >
          + إضافة مركز
        </button>
      </div>

      {error ? <p className="text-sm text-bsr-market-down">{error}</p> : null}

      <button
        type="submit"
        disabled={submitting}
        className="self-start rounded-bsr-md bg-bsr-gold-500 px-bsr-5 py-bsr-2 font-semibold text-bsr-navy-950 hover:bg-bsr-gold-400 disabled:opacity-60"
      >
        {submitting ? "جارٍ التحليل..." : "تحليل المحفظة"}
      </button>
    </form>
  );
}
