"use client";

import { useEffect, useState } from "react";
import { AiStar } from "@/components/ai/AiStar";
import { EmptyState } from "@/components/patterns/EmptyState";
import { LoadingScreen } from "@/components/patterns/LoadingScreen";
import { PortfolioForm } from "@/components/portfolio/PortfolioForm";
import { PortfolioDetail } from "@/components/portfolio/PortfolioDetail";
import { ApiError } from "@/lib/api/client";
import { getPortfolio } from "@/lib/api/portfolio";
import type { PortfolioAnalysis } from "@/lib/api/portfolio-types";
import {
  clearStoredPortfolioId,
  getStoredPortfolioId,
  setStoredPortfolioId,
} from "@/lib/portfolio/local-portfolio";

type ViewState =
  | { mode: "loading" }
  | { mode: "form"; editing?: PortfolioAnalysis }
  | { mode: "detail"; analysis: PortfolioAnalysis };

export default function PortfolioPage() {
  const [storedId] = useState<number | null>(() => getStoredPortfolioId());
  const [state, setState] = useState<ViewState>(() =>
    storedId == null ? { mode: "form" } : { mode: "loading" }
  );

  useEffect(() => {
    if (storedId == null) return;
    let cancelled = false;
    getPortfolio(storedId)
      .then((analysis) => {
        if (!cancelled) setState({ mode: "detail", analysis });
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        if (
          error instanceof ApiError &&
          (error.code === "portfolio_not_found" || error.code === "no_portfolio_analysis")
        ) {
          clearStoredPortfolioId();
          setState({ mode: "form" });
        } else {
          setState({ mode: "form" });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [storedId]);

  if (state.mode === "loading") {
    return <LoadingScreen />;
  }

  if (state.mode === "form") {
    const editing = state.editing;
    return (
      <div className="flex flex-col gap-bsr-4">
        <div className="flex items-center gap-bsr-2">
          <AiStar size="lg" />
          <h1 className="text-lg font-semibold text-bsr-text-primary">المحفظة</h1>
        </div>
        {!editing ? (
          <EmptyState
            title="لم يتم تحليل أي محفظة بعد"
            description="أضف مراكزك لتحصل على تحليل شامل: التوزيع، المخاطر، التنويع، وتوصيات إعادة التوازن."
          />
        ) : null}
        <PortfolioForm
          portfolioId={editing?.portfolio_id}
          initialName={editing?.name}
          initialCash={editing?.cash}
          initialHoldings={editing?.holdings.map((h) => ({
            symbol: h.symbol,
            quantity: h.quantity,
            averageCost: h.average_cost,
          }))}
          onAnalyzed={(analysis) => {
            setStoredPortfolioId(analysis.portfolio_id);
            setState({ mode: "detail", analysis });
          }}
        />
      </div>
    );
  }

  return (
    <PortfolioDetail
      analysis={state.analysis}
      onEdit={() => setState({ mode: "form", editing: state.analysis })}
      onReset={() => {
        clearStoredPortfolioId();
        setState({ mode: "form" });
      }}
    />
  );
}
