import { Suspense } from "react";
import { LoadingScreen } from "@/components/patterns/LoadingScreen";
import { VerifyEmailClient } from "./VerifyEmailClient";

export default function VerifyEmailPage() {
  return (
    <Suspense fallback={<LoadingScreen />}>
      <VerifyEmailClient />
    </Suspense>
  );
}
