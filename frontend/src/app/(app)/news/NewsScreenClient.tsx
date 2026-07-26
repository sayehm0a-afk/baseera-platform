"use client";

import { useState, type FormEvent } from "react";
import { useSearchParams } from "next/navigation";
import { EmptyState } from "@/components/patterns/EmptyState";
import { LoadingScreen } from "@/components/patterns/LoadingScreen";
import { SentimentBadge } from "@/components/badges/SentimentBadge";
import { getMarketNews, getSymbolNews } from "@/lib/api/news";
import { useCategoryFetch } from "@/lib/hooks/useCategoryFetch";
import { NEWS_CATEGORY_LABELS } from "@/lib/news-labels";
import type { NewsEvent } from "@/lib/api/news-types";

async function fetchNews(symbol: string): Promise<NewsEvent[]> {
  const feed = symbol === "" ? await getMarketNews() : await getSymbolNews(symbol);
  return feed.events;
}

function EntityChip({ entity }: { entity: NewsEvent["entities"][number] }) {
  const text = entity.symbol ?? entity.sector ?? entity.label ?? entity.entity_type;
  return (
    <span className="inline-flex items-center rounded-bsr-full bg-bsr-surface-overlay px-bsr-2 py-0.5 text-xs text-bsr-text-secondary">
      {text}
    </span>
  );
}

function NewsCard({ event }: { event: NewsEvent }) {
  const isAnalyzed = event.analyzed_at != null;

  return (
    <li className="flex flex-col gap-bsr-2 rounded-bsr-lg border border-bsr-border-subtle bg-bsr-surface-raised p-bsr-4">
      <div className="flex flex-wrap items-start justify-between gap-bsr-2">
        <p className="text-sm font-medium leading-6 text-bsr-text-primary">{event.headline}</p>
        {event.sentiment_label ? (
          <SentimentBadge label={event.sentiment_label} />
        ) : null}
      </div>

      <div className="flex flex-wrap items-center gap-bsr-2 text-xs text-bsr-text-muted">
        <span>{event.source}</span>
        {event.published_at ? (
          <>
            <span>·</span>
            <span>{new Date(event.published_at).toLocaleString("ar-SA")}</span>
          </>
        ) : null}
        {event.is_synthetic ? (
          <span className="rounded-bsr-sm bg-bsr-action-watch/15 px-bsr-2 py-0.5 text-bsr-action-watch">
            بيانات تطويرية
          </span>
        ) : null}
        {event.duplicate_count > 0 ? (
          <span>· {event.duplicate_count} نسخة مكررة مدمجة</span>
        ) : null}
      </div>

      {event.entities.length > 0 ? (
        <div className="flex flex-wrap gap-bsr-1">
          {event.entities.map((entity, index) => (
            <EntityChip key={index} entity={entity} />
          ))}
        </div>
      ) : null}

      {isAnalyzed ? (
        <>
          <div className="flex flex-wrap items-center gap-bsr-3 text-xs text-bsr-text-secondary">
            {event.category ? (
              <span className="rounded-bsr-full bg-bsr-surface-overlay px-bsr-3 py-1 text-bsr-text-primary">
                {NEWS_CATEGORY_LABELS[event.category] ?? event.category}
              </span>
            ) : null}
            {event.confidence != null ? (
              <span>نسبة الثقة: {Math.round(event.confidence)}%</span>
            ) : null}
          </div>
          {event.explanation ? (
            <p className="text-sm text-bsr-text-secondary">{event.explanation}</p>
          ) : null}
        </>
      ) : (
        <p className="text-xs text-bsr-text-muted">بانتظار تحليل بصيرة AI لهذا الخبر.</p>
      )}
    </li>
  );
}

export function NewsScreenClient() {
  const searchParams = useSearchParams();
  const [symbol, setSymbol] = useState(searchParams.get("symbol") ?? "");
  const [query, setQuery] = useState(searchParams.get("symbol") ?? "");
  const state = useCategoryFetch(query, fetchNews);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setQuery(symbol.trim());
  }

  return (
    <div className="flex flex-col gap-bsr-4">
      <h1 className="text-lg font-semibold text-bsr-text-primary">الأخبار</h1>

      <form onSubmit={handleSubmit} className="flex gap-bsr-2">
        <input
          value={symbol}
          onChange={(e) => setSymbol(e.target.value)}
          placeholder="ابحث عن أخبار سهم معيّن (مثال: 2222) -- اتركه فارغاً لأخبار السوق العامة"
          className="bsr-numeric flex-1 rounded-bsr-md border border-bsr-border-subtle bg-bsr-surface-raised px-bsr-4 py-bsr-2 text-bsr-text-primary focus:border-bsr-gold-500 focus:outline-none"
        />
        <button
          type="submit"
          className="rounded-bsr-md bg-bsr-gold-500 px-bsr-5 py-bsr-2 font-semibold text-bsr-navy-950 hover:bg-bsr-gold-400"
        >
          بحث
        </button>
        {symbol !== "" || query !== "" ? (
          <button
            type="button"
            onClick={() => {
              setSymbol("");
              setQuery("");
            }}
            className="rounded-bsr-md border border-bsr-border-subtle px-bsr-4 py-bsr-2 text-sm text-bsr-text-secondary hover:bg-bsr-surface-overlay"
          >
            أخبار السوق
          </button>
        ) : null}
      </form>

      <p className="text-sm text-bsr-text-secondary">
        {query === "" ? "أخبار السوق العامة والحكومية" : `أخبار سهم ${query}`}
      </p>

      {state.status === "loading" ? <LoadingScreen /> : null}

      {state.status === "error" ? (
        <EmptyState
          title="تعذّر تحميل الأخبار"
          description="تأكد من اتصال الخادم وحاول مرة أخرى."
        />
      ) : null}

      {state.status === "ready" && state.entries.length === 0 ? (
        <EmptyState
          title={query === "" ? "لا توجد أخبار سوقية حالياً" : "لا توجد أخبار لهذا الرمز حالياً"}
        />
      ) : null}

      {state.status === "ready" && state.entries.length > 0 ? (
        <ul className="flex flex-col gap-bsr-3">
          {state.entries.map((event) => (
            <NewsCard key={event.id} event={event} />
          ))}
        </ul>
      ) : null}
    </div>
  );
}
