"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { AiStar } from "@/components/ai/AiStar";
import { verifyEmail } from "@/lib/auth/auth-service";

type Status = "verifying" | "success" | "error";

export function VerifyEmailClient() {
  const searchParams = useSearchParams();
  const token = searchParams.get("token");
  const [status, setStatus] = useState<Status>(token ? "verifying" : "error");

  useEffect(() => {
    if (!token) {
      return;
    }
    verifyEmail(token)
      .then(() => setStatus("success"))
      .catch(() => setStatus("error"));
  }, [token]);

  return (
    <div className="flex flex-1 items-center justify-center px-bsr-4">
      <div className="w-full max-w-sm rounded-bsr-lg border border-bsr-border-subtle bg-bsr-surface-raised p-bsr-6 text-center shadow-bsr-raised">
        <div className="mb-bsr-6 flex flex-col items-center gap-bsr-2">
          <AiStar
            size="lg"
            className={
              status === "verifying"
                ? "animate-[bsr-pulse_1s_ease-in-out_infinite]"
                : undefined
            }
          />
          <div className="flex items-baseline gap-bsr-2">
            <span className="text-xl font-semibold text-bsr-white">بصيرة</span>
            <span className="text-xl font-semibold text-bsr-teal-500">AI</span>
          </div>
        </div>

        {status === "verifying" ? (
          <p className="text-sm text-bsr-text-secondary">
            جارٍ تأكيد بريدك الإلكتروني...
          </p>
        ) : status === "success" ? (
          <div className="flex flex-col gap-bsr-4">
            <p className="text-sm leading-7 text-bsr-text-primary">
              تم تأكيد بريدك الإلكتروني بنجاح. يمكنك الآن تسجيل الدخول.
            </p>
            <Link
              href="/login"
              className="rounded-bsr-md bg-bsr-gold-500 px-bsr-4 py-bsr-2 font-semibold text-bsr-navy-950 transition-colors hover:bg-bsr-gold-400"
            >
              تسجيل الدخول
            </Link>
          </div>
        ) : (
          <div className="flex flex-col gap-bsr-4">
            <p role="alert" className="text-sm leading-7 text-bsr-market-down">
              رابط التأكيد غير صالح أو منتهي الصلاحية.
            </p>
            <Link
              href="/login"
              className="text-sm text-bsr-gold-500 hover:text-bsr-gold-400"
            >
              العودة إلى تسجيل الدخول
            </Link>
          </div>
        )}
      </div>
    </div>
  );
}
