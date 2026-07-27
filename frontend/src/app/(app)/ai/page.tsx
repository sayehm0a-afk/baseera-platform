import { Suspense } from "react";
import { LoadingScreen } from "@/components/patterns/LoadingScreen";
import { AiScreenClient } from "./AiScreenClient";

export default function AiPage() {
  return (
    <Suspense fallback={<LoadingScreen />}>
      <AiScreenClient />
    </Suspense>
  );
}
