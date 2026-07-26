import { Suspense } from "react";
import { LoadingScreen } from "@/components/patterns/LoadingScreen";
import { NewsScreenClient } from "./NewsScreenClient";

export default function NewsPage() {
  return (
    <Suspense fallback={<LoadingScreen />}>
      <NewsScreenClient />
    </Suspense>
  );
}
