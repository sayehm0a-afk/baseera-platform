/**
 * TEMPORARY PLACEHOLDER -- no `/api/v1/news/*` backend endpoint exists
 * yet (no news ingestion/service layer anywhere in `src/`). Per the
 * Phase 9 brief, this is a disclosed, isolated placeholder only: it
 * never returns fabricated headlines, and its shape mirrors what a
 * future news client would look like so the News screen already knows
 * how to consume real data the moment a backend endpoint exists --
 * only this file and the screen's "unavailable" branch would change.
 */

export interface NewsItem {
  id: string;
  headline: string;
  source: string;
  publishedAt: string;
  symbol: string | null;
}

export interface NewsFeedResult {
  available: false;
  reason: string;
}

export async function getNewsFeed(): Promise<NewsFeedResult> {
  return {
    available: false,
    reason: "لا يوجد مصدر أخبار متصل بعد -- بانتظار ربط واجهة برمجة التطبيقات الخاصة بالأخبار.",
  };
}
