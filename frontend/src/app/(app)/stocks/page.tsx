"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { EmptyState } from "@/components/patterns/EmptyState";
import { LoadingScreen } from "@/components/patterns/LoadingScreen";
import { StockDirectoryRow } from "@/components/stocks/StockDirectoryRow";
import { getStockDirectory } from "@/lib/api/stocks";
import type { StockDirectoryItem } from "@/lib/api/stocks-types";

const PAGE_SIZE = 30;

type DirectoryState =
  | { status: "loading" }
  | { status: "error" }
  | { status: "ready"; items: StockDirectoryItem[]; total: number; hasMore: boolean };

/** All-Stocks directory (RADAR-C Phase F) -- browses the full Saudi
 * market via GET /api/v1/stocks/directory, which reads only already-
 * persisted PriceBar rows (no live SAHMK call, ever -- see that
 * route's own docstring). Search is server-side (same Arabic-name/
 * symbol matching /search already uses) with a short debounce so
 * typing doesn't spam requests. */
export default function StocksDirectoryPage() {
  const [query, setQuery] = useState("");
  const [state, setState] = useState<DirectoryState>({ status: "loading" });
  const [loadingMore, setLoadingMore] = useState(false);
  const generation = useRef(0);
  const pagePending = useRef(false);

  const load = useCallback((q: string, offset: number, append: boolean, requestGeneration: number) => {
    if (append && pagePending.current) return;
    pagePending.current = true;
    setLoadingMore(append);
    getStockDirectory({ q: q || undefined, limit: PAGE_SIZE, offset })
      .then((result) => {
        if (requestGeneration !== generation.current) return;
        setState((prev) => {
          const previousItems = append && prev.status === "ready" ? prev.items : [];
          const items = [...previousItems, ...result.results];
          return {
            status: "ready",
            items,
            total: result.total,
            hasMore: items.length < result.total,
          };
        });
      })
      .catch(() => {
        if (requestGeneration === generation.current) setState({ status: "error" });
      })
      .finally(() => {
        if (requestGeneration === generation.current) {
          pagePending.current = false;
          setLoadingMore(false);
        }
      });
  }, []);

  useEffect(() => {
    const trimmed = query.trim();
    const requestGeneration = ++generation.current;
    pagePending.current = false;
    const timer = setTimeout(() => {
      setState({ status: "loading" });
      load(trimmed, 0, false, requestGeneration);
    }, 300);
    return () => {
      clearTimeout(timer);
      generation.current += 1;
    };
  }, [query, load]);

  return (
    <div className="flex flex-col gap-bsr-4">
      <div>
        <h1 className="text-lg font-semibold text-bsr-text-primary">جميع الأسهم</h1>
        <p className="mt-1 text-sm text-bsr-text-secondary">تصفح الشركات السعودية المتاحة في مصدر البيانات المتصل وابحث عنها بالاسم أو الرمز.</p>
      </div>

      <label>
        <span className="sr-only">ابحث برمز السهم أو اسم الشركة</span>
        <input
          type="search"
          value={query}
          onChange={(event) => {
            generation.current += 1;
            pagePending.current = false;
            setState({ status: "loading" });
            setQuery(event.target.value);
          }}
          placeholder="ابحث برمز السهم أو اسم الشركة..."
          className="w-full rounded-bsr-full border border-bsr-border-subtle bg-bsr-surface-raised px-bsr-4 py-bsr-2 text-sm text-bsr-text-primary placeholder:text-bsr-text-muted focus:border-bsr-gold-500 focus:outline-none"
        />
      </label>

      {state.status === "loading" ? <LoadingScreen /> : null}

      {state.status === "error" ? (
        <EmptyState
          title="تعذّر تحميل قائمة الأسهم"
          description="تأكد من اتصال الخادم وحاول مرة أخرى."
        />
      ) : null}

      {state.status === "ready" && state.items.length === 0 ? (
        <EmptyState
          title={query.trim() ? "لا توجد نتائج" : "قائمة الشركات غير متاحة حاليًا"}
          description={query.trim()
            ? "لم يُعثر على تطابق ضمن الشركات المتاحة. جرّب الرمز أو اسمًا آخر؛ قد تكون تغطية البيانات ناقصة."
            : "لم تصل قائمة شركات قابلة للعرض. لا يعني ذلك عدم وجود شركات مدرجة في السوق."}
        />
      ) : null}

      {state.status === "ready" && state.items.length > 0 ? (
        <div className="flex flex-col gap-bsr-2">
          {state.items.map((item) => (
            <StockDirectoryRow key={item.symbol} item={item} />
          ))}
          {state.hasMore ? (
            <button
              type="button"
              disabled={loadingMore}
              onClick={() => load(query.trim(), state.items.length, true, generation.current)}
              className="mt-bsr-2 rounded-bsr-md border border-bsr-border-subtle px-bsr-4 py-bsr-2 text-sm font-semibold text-bsr-text-primary transition-colors hover:border-bsr-gold-500/40"
            >
              {loadingMore ? "جارٍ التحميل..." : "تحميل المزيد"}
            </button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
