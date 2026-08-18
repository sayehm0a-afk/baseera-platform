"use client";

import { useCallback, useEffect, useState } from "react";
import { AiStar } from "@/components/ai/AiStar";
import { EmptyState } from "@/components/patterns/EmptyState";
import { ExpandableSection } from "@/components/patterns/ExpandableSection";
import { LoadingScreen } from "@/components/patterns/LoadingScreen";
import { AddHoldingForm } from "@/components/portfolio/AddHoldingForm";
import { HoldingRow } from "@/components/portfolio/HoldingRow";
import { PortfolioDetail } from "@/components/portfolio/PortfolioDetail";
import { ApiError } from "@/lib/api/client";
import {
  addPortfolioHolding,
  analyzePortfolio,
  createPortfolio,
  deletePortfolioHolding,
  getPortfolioHoldings,
  listMyPortfolios,
  updatePortfolioHolding,
} from "@/lib/api/portfolio";
import type { PortfolioAnalysis, PortfolioHoldings } from "@/lib/api/portfolio-types";
import { setStoredPortfolioId } from "@/lib/portfolio/local-portfolio";

type State =
  | { status: "loading" }
  | { status: "error" }
  | { status: "ready"; portfolioId: number; holdings: PortfolioHoldings };

function fmt(value: number | null | undefined): string {
  return value == null ? "—" : value.toFixed(2);
}

/** RADAR-C Phase H: Smart Portfolio -- real, persisted holdings CRUD
 * (GET/POST/PATCH/DELETE /api/v1/portfolio/{id}/holdings) with
 * computed P&L from already-persisted prices and per-holding "already
 * own this -- what now" guidance. Never triggers a live SAHMK call on
 * its own: only the opt-in "تحليل شامل" (full analysis) button below
 * does, via the existing POST /analyze surface, exactly as before. */
export default function PortfolioPage() {
  const [state, setState] = useState<State>({ status: "loading" });
  const [fullAnalysis, setFullAnalysis] = useState<PortfolioAnalysis | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [analyzeError, setAnalyzeError] = useState<string | null>(null);

  const loadHoldings = useCallback(async (portfolioId: number) => {
    const holdings = await getPortfolioHoldings(portfolioId);
    setState({ status: "ready", portfolioId, holdings });
  }, []);

  const bootstrap = useCallback(async (): Promise<State> => {
    try {
      const { portfolios } = await listMyPortfolios();
      const portfolioId =
        portfolios.length > 0 ? portfolios[0].id : (await createPortfolio({ name: "محفظتي" })).id;
      const holdings = await getPortfolioHoldings(portfolioId);
      return { status: "ready", portfolioId, holdings };
    } catch {
      return { status: "error" };
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    bootstrap().then((result) => {
      if (!cancelled) setState(result);
    });
    return () => {
      cancelled = true;
    };
  }, [bootstrap]);

  async function handleAdd(symbol: string, quantity: number, averageCost: number | undefined) {
    if (state.status !== "ready") return;
    try {
      await addPortfolioHolding(state.portfolioId, { symbol, quantity, average_cost: averageCost });
    } catch (error: unknown) {
      if (error instanceof ApiError && error.code === "duplicate_holding") {
        throw new Error("هذا السهم موجود بالفعل في محفظتك -- عدّل الكمية بدلاً من إضافته من جديد.");
      }
      throw error;
    }
    await loadHoldings(state.portfolioId);
  }

  async function handleUpdate(holdingId: number, quantity: number, averageCost: number | undefined) {
    if (state.status !== "ready") return;
    await updatePortfolioHolding(state.portfolioId, holdingId, { quantity, average_cost: averageCost });
    await loadHoldings(state.portfolioId);
  }

  async function handleDelete(holdingId: number) {
    if (state.status !== "ready") return;
    await deletePortfolioHolding(state.portfolioId, holdingId);
    await loadHoldings(state.portfolioId);
  }

  async function handleRunFullAnalysis() {
    if (state.status !== "ready") return;
    setAnalyzing(true);
    setAnalyzeError(null);
    try {
      const analysis = await analyzePortfolio({
        portfolio_id: state.portfolioId,
        name: state.holdings.name,
        cash: state.holdings.cash_balance,
        holdings: state.holdings.holdings.map((h) => ({
          symbol: h.symbol,
          quantity: h.quantity,
          average_cost: h.average_cost ?? undefined,
        })),
      });
      setStoredPortfolioId(analysis.portfolio_id);
      setFullAnalysis(analysis);
    } catch {
      setAnalyzeError("تعذّر تشغيل التحليل الشامل. حاول مرة أخرى بعد قليل.");
    } finally {
      setAnalyzing(false);
    }
  }

  if (state.status === "loading") {
    return <LoadingScreen />;
  }

  if (state.status === "error") {
    return (
      <EmptyState
        title="تعذّر تحميل محفظتك"
        description="حدث خطأ أثناء الاتصال بالخادم. حاول مرة أخرى بعد قليل."
      />
    );
  }

  const { holdings: data } = state;
  const totalPnlColorClass =
    data.total_unrealized_pnl == null
      ? "text-bsr-text-secondary"
      : data.total_unrealized_pnl > 0
        ? "text-bsr-market-up"
        : data.total_unrealized_pnl < 0
          ? "text-bsr-market-down"
          : "text-bsr-text-secondary";

  return (
    <div className="flex flex-col gap-bsr-4">
      <div className="flex items-center gap-bsr-2">
        <AiStar size="lg" />
        <h1 className="text-lg font-semibold text-bsr-text-primary">محفظتي الذكية</h1>
      </div>

      <div className="grid grid-cols-2 gap-bsr-3 md:grid-cols-4">
        <div className="flex flex-col gap-bsr-1 rounded-bsr-md bg-bsr-surface-overlay px-bsr-4 py-bsr-3">
          <span className="text-xs text-bsr-text-secondary">التكلفة المستثمرة</span>
          <span className="bsr-numeric text-xl font-semibold text-bsr-text-primary">
            {fmt(data.total_invested_cost)}
          </span>
        </div>
        <div className="flex flex-col gap-bsr-1 rounded-bsr-md bg-bsr-surface-overlay px-bsr-4 py-bsr-3">
          <span className="text-xs text-bsr-text-secondary">القيمة الحالية</span>
          <span className="bsr-numeric text-xl font-semibold text-bsr-text-primary">
            {fmt(data.total_current_value)}
          </span>
        </div>
        <div className="flex flex-col gap-bsr-1 rounded-bsr-md bg-bsr-surface-overlay px-bsr-4 py-bsr-3">
          <span className="text-xs text-bsr-text-secondary">الربح/الخسارة غير المحقق</span>
          <span className={`bsr-numeric text-xl font-semibold ${totalPnlColorClass}`}>
            {fmt(data.total_unrealized_pnl)}
            {data.total_unrealized_pnl_pct != null ? ` (${data.total_unrealized_pnl_pct.toFixed(2)}%)` : ""}
          </span>
        </div>
        <div className="flex flex-col gap-bsr-1 rounded-bsr-md bg-bsr-surface-overlay px-bsr-4 py-bsr-3">
          <span className="text-xs text-bsr-text-secondary">القيمة الإجمالية مع النقد</span>
          <span className="bsr-numeric text-xl font-semibold text-bsr-text-primary">
            {fmt(data.total_value_with_cash)}
          </span>
        </div>
      </div>

      <AddHoldingForm onAdd={handleAdd} />

      {data.holdings.length === 0 ? (
        <EmptyState
          title="لم تتم إضافة أي سهم بعد"
          description="أضف أول سهم تملكه أعلاه لتتابع أداءه ومتى يجب الاحتفاظ به أو مراقبته أو تخفيفه أو الخروج منه."
        />
      ) : (
        <div className="flex flex-col gap-bsr-2">
          {data.holdings.map((holding) => (
            <HoldingRow
              key={holding.id}
              holding={holding}
              onUpdate={(quantity, averageCost) => handleUpdate(holding.id, quantity, averageCost)}
              onDelete={() => handleDelete(holding.id)}
            />
          ))}
        </div>
      )}

      {data.holdings.length > 0 ? (
        <ExpandableSection
          title="التحليل الشامل للمحفظة"
          subtitle="التوزيع، المخاطر، التنويع، وتوصيات إعادة التوازن -- يتطلب تشغيل تحليل جديد"
        >
          {fullAnalysis ? (
            <PortfolioDetail
              analysis={fullAnalysis}
              onEdit={() => setFullAnalysis(null)}
              onReset={() => setFullAnalysis(null)}
            />
          ) : (
            <div className="flex flex-col items-start gap-bsr-2">
              <p className="text-sm text-bsr-text-secondary">
                يشغّل هذا التحليل محرك بصيرة الكامل (التوزيع، المخاطر، التنويع، إعادة التوازن) على مراكزك الحالية.
              </p>
              <button
                type="button"
                onClick={handleRunFullAnalysis}
                disabled={analyzing}
                className="rounded-bsr-md bg-bsr-gold-500 px-bsr-5 py-bsr-2 font-semibold text-bsr-navy-950 hover:bg-bsr-gold-400 disabled:opacity-60"
              >
                {analyzing ? "جارٍ التحليل..." : "تشغيل التحليل الشامل"}
              </button>
              {analyzeError ? <p className="text-sm text-bsr-market-down">{analyzeError}</p> : null}
            </div>
          )}
        </ExpandableSection>
      ) : null}
    </div>
  );
}
