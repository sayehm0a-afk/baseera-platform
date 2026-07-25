import { EmptyState } from "@/components/patterns/EmptyState";
import { getNewsFeed } from "@/lib/api/news";

export default async function NewsPage() {
  const feed = await getNewsFeed();

  return (
    <div className="flex flex-col gap-bsr-4">
      <h1 className="text-lg font-semibold text-bsr-text-primary">الأخبار</h1>
      <EmptyState
        title="مصدر الأخبار قيد الربط"
        description={feed.reason}
      />
    </div>
  );
}
