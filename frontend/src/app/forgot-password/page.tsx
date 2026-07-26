"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import { AiStar } from "@/components/ai/AiStar";
import { forgotPassword } from "@/lib/auth/auth-service";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isSubmitted, setIsSubmitted] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!email.trim()) {
      return;
    }
    setIsSubmitting(true);
    try {
      // The backend always returns the same generic message whether or
      // not the email exists (src/api/routes/auth.py) -- never surface
      // a distinguishing error here, that would leak account existence.
      await forgotPassword(email.trim());
    } finally {
      setIsSubmitting(false);
      setIsSubmitted(true);
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

        {isSubmitted ? (
          <div className="flex flex-col items-center gap-bsr-4 text-center">
            <p className="text-sm leading-7 text-bsr-text-primary">
              إذا كان هذا البريد الإلكتروني مسجّلاً لدينا، فستصلك رسالة تحتوي على
              رابط لإعادة تعيين كلمة المرور.
            </p>
            <Link
              href="/login"
              className="text-sm text-bsr-gold-500 hover:text-bsr-gold-400"
            >
              العودة إلى تسجيل الدخول
            </Link>
          </div>
        ) : (
          <form className="flex flex-col gap-bsr-4" onSubmit={handleSubmit} noValidate>
            <p className="text-sm leading-7 text-bsr-text-secondary">
              أدخل بريدك الإلكتروني وسنرسل لك رابطاً لإعادة تعيين كلمة المرور.
            </p>

            <label className="flex flex-col gap-bsr-1">
              <span className="text-sm text-bsr-text-secondary">
                البريد الإلكتروني
              </span>
              <input
                type="email"
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="rounded-bsr-md border border-bsr-border-subtle bg-bsr-surface-base px-bsr-3 py-bsr-2 text-bsr-text-primary focus:border-bsr-gold-500 focus:outline-none"
              />
            </label>

            <button
              type="submit"
              disabled={isSubmitting}
              className="mt-bsr-2 rounded-bsr-md bg-bsr-gold-500 px-bsr-4 py-bsr-2 font-semibold text-bsr-navy-950 transition-colors hover:bg-bsr-gold-400 disabled:opacity-50"
            >
              {isSubmitting ? "جارٍ الإرسال..." : "إرسال رابط إعادة التعيين"}
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
