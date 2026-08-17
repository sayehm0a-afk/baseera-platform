"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { AiStar } from "@/components/ai/AiStar";
import { fetchSession } from "@/lib/auth/auth-service";

const SPLASH_DURATION_MS = 900;

/** Splash screen -- shows the mark, then routes to the dashboard for
 * an already-signed-in session (a real GET /auth/me, resolved against
 * the httpOnly cookies the browser already sent) or to /login otherwise. */
export default function SplashPage() {
  const router = useRouter();

  useEffect(() => {
    const timer = setTimeout(() => {
      fetchSession().then((user) => {
        router.replace(user ? "/radar" : "/login");
      });
    }, SPLASH_DURATION_MS);
    return () => clearTimeout(timer);
  }, [router]);

  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-bsr-4">
      <div className="relative">
        <AiStar size="lg" className="animate-[bsr-pulse_1s_ease-in-out_infinite]" />
      </div>
      <div className="flex items-baseline gap-bsr-2">
        <span className="text-2xl font-semibold text-bsr-white">بصيرة</span>
        <span className="text-2xl font-semibold text-bsr-teal-500">AI</span>
      </div>
      <p className="text-sm text-bsr-text-secondary">
        الذكاء الاصطناعي لتحليل السوق السعودي
      </p>
    </div>
  );
}
