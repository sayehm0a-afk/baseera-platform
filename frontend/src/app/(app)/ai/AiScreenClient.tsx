"use client";

import { useState, type FormEvent } from "react";
import { useSearchParams } from "next/navigation";
import { AiStar } from "@/components/ai/AiStar";
import { AnalystReportView } from "@/components/ai/AnalystReportView";
import { EmptyState } from "@/components/patterns/EmptyState";
import { LoadingScreen } from "@/components/patterns/LoadingScreen";
import { getAnalystReport } from "@/lib/api/stocks";
import { useCategoryFetch } from "@/lib/hooks/useCategoryFetch";
import type { AnalystReport } from "@/lib/api/stocks-types";

async function fetchReport(symbol: string): Promise<AnalystReport[]> {
  if (!symbol) return [];
  const report = await getAnalystReport(symbol);
  return [report];
}

export function AiScreenClient() {
  const searchParams = useSearchParams();
  const [symbol, setSymbol] = useState(searchParams.get("symbol") ?? "");
  const [query, setQuery] = useState(searchParams.get("symbol") ?? "");
  const state = useCategoryFetch(query, fetchReport);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setQuery(symbol.trim());
  }

  return (
    <div className="flex flex-col gap-bsr-4">
      <div className="flex items-center gap-bsr-2">
        <AiStar size="lg" />
        <h1 className="text-lg font-semibold text-bsr-text-primary">الذكاء الاصطناعي</h1>
      </div>

      <form onSubmit={handleSubmit} className="flex gap-bsr-2">
        <input
          value={symbol}
          onChange={(e) => setSymbol(e.target.value)}
          placeholder="أدخل رمز السهم (مثال: 2222)"
          className="bsr-numeric flex-1 rounded-bsr-md border border-bsr-border-subtle bg-bsr-surface-raised px-bsr-4 py-bsr-2 text-bsr-text-primary focus:border-bsr-gold-500 focus:outline-none"
        />
        <button
          type="submit"
          className="rounded-bsr-md bg-bsr-gold-500 px-bsr-5 py-bsr-2 font-semibold text-bsr-navy-950 hover:bg-bsr-gold-400"
        >
          تحليل
        </button>
      </form>

      {query === "" ? (
        <EmptyState
          title="اطلب تحليل بصيرة AI لأي سهم"
          description="أدخل رمز السهم للحصول على تقرير تحليلي كامل: التوصية، الثقة، الأهداف، والتفسير الكامل."
        />
      ) : null}

      {query !== "" && state.status === "loading" ? <LoadingScreen /> : null}

      {query !== "" && state.status === "unavailable" ? (
        <EmptyState title="لا تتوفر بيانات كافية لتحليل هذا السهم" />
      ) : null}

      {query !== "" && state.status === "error" ? (
        <EmptyState
          title="تعذّر إيجاد هذا الرمز"
          description="تحقق من رمز السهم وحاول مرة أخرى."
        />
      ) : null}

      {query !== "" && state.status === "ready" && state.entries[0] ? (
        <AnalystReportView report={state.entries[0]} />
      ) : null}
    </div>
  );
}
