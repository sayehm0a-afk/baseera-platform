import { Suspense } from "react";
import { LoadingScreen } from "@/components/patterns/LoadingScreen";
import { StockDetailClient } from "./StockDetailClient";

export default async function StockDetailPage({
  params,
}: {
  params: Promise<{ symbol: string }>;
}) {
  const { symbol } = await params;
  return (
    <Suspense fallback={<LoadingScreen />}>
      <StockDetailClient symbol={decodeURIComponent(symbol)} />
    </Suspense>
  );
}
