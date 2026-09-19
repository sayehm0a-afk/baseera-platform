"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { AiStar } from "@/components/ai/AiStar";
import { ApiError } from "@/lib/api/client";
import { resetPassword } from "@/lib/auth/auth-service";

// Mirrors src/api/schemas/auth.py's _validate_password_complexity --
// see register/page.tsx's identical constant/helper for the full
// rationale (shown up front since the backend's 422 validation error
// isn't wrapped in {"error": {code, message}}, so it can't be mapped
// to a specific client-facing message).
const PASSWORD_HINT = "8 أحرف على الأقل، تتضمن حرفًا ورقمًا.";

function passwordMeetsPolicy(value: string): boolean {
  return value.length >= 8 && /\p{L}/u.test(value) && /\d/.test(value);
}

export function ResetPasswordClient() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const token = searchParams.get("token");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isDone, setIsDone] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token) {
      setError("رابط إعادة التعيين غير صالح.");
      return;
    }
    if (!password.trim()) {
      setError("يرجى إدخال كلمة مرور جديدة.");
      return;
    }
    if (!passwordMeetsPolicy(password)) {
      setError(`كلمة المرور لا تحقق الشروط المطلوبة: ${PASSWORD_HINT}`);
      return;
    }
    setError(null);
    setIsSubmitting(true);
    try {
      await resetPassword(token, password);
      setIsDone(true);
    } catch (err) {
      const code = err instanceof ApiError ? err.code : null;
      setError(
        code === "invalid_or_expired_token"
          ? "رابط إعادة التعيين غير صالح أو منتهي الصلاحية."
          : "تعذّرت إعادة تعيين كلمة المرور. يرجى المحاولة مرة أخرى."
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="flex flex-1 items-center justify-center px-bsr-4">
      <div className="w-full max-w-sm rounded-bsr-lg border border-bsr-border-subtle bg-bsr-surface-raised p-bsr-6 shadow-bsr-raised">
        <div className="mb-bsr-6 flex flex-col items-center gap-bsr-2">
          <AiStar size="lg" />
          <div className="flex items-baseline gap-bsr-2">
            <span className="text-xl font-semibold text-bsr-white">بصيرة</span>
            <span className="text-xl font-semibold text-bsr-teal-500">AI</span>
          </div>
        </div>

        {isDone ? (
          <div className="flex flex-col items-center gap-bsr-4 text-center">
            <p className="text-sm leading-7 text-bsr-text-primary">
              تم تغيير كلمة المرور بنجاح. يرجى تسجيل الدخول بكلمة المرور الجديدة.
            </p>
            <button
              type="button"
              onClick={() => router.replace("/login")}
              className="rounded-bsr-md bg-bsr-gold-500 px-bsr-4 py-bsr-2 font-semibold text-bsr-navy-950 transition-colors hover:bg-bsr-gold-400"
            >
              تسجيل الدخول
            </button>
          </div>
        ) : (
          <form className="flex flex-col gap-bsr-4" onSubmit={handleSubmit} noValidate>
            <label className="flex flex-col gap-bsr-1">
              <span className="text-sm text-bsr-text-secondary">
                كلمة المرور الجديدة
              </span>
              <input
                type="password"
                autoComplete="new-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="rounded-bsr-md border border-bsr-border-subtle bg-bsr-surface-base px-bsr-3 py-bsr-2 text-bsr-text-primary focus:border-bsr-gold-500 focus:outline-none"
              />
              <span className="text-xs text-bsr-text-muted">{PASSWORD_HINT}</span>
            </label>

            {error ? (
              <p role="alert" className="text-sm text-bsr-market-down">
                {error}
              </p>
            ) : null}

            <button
              type="submit"
              disabled={isSubmitting}
              className="mt-bsr-2 rounded-bsr-md bg-bsr-gold-500 px-bsr-4 py-bsr-2 font-semibold text-bsr-navy-950 transition-colors hover:bg-bsr-gold-400 disabled:opacity-50"
            >
              {isSubmitting ? "جارٍ التحديث..." : "تحديث كلمة المرور"}
            </button>

            <p className="text-center text-sm text-bsr-text-secondary">
              <Link href="/login" className="text-bsr-gold-500 hover:text-bsr-gold-400">
                العودة إلى تسجيل الدخول
              </Link>
            </p>
          </form>
        )}
      </div>
    </div>
  );
}
