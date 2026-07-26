import { Suspense } from "react";
import { LoadingScreen } from "@/components/patterns/LoadingScreen";
import { ResetPasswordClient } from "./ResetPasswordClient";

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={<LoadingScreen />}>
      <ResetPasswordClient />
    </Suspense>
  );
}
