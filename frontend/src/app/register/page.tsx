"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import { AiStar } from "@/components/ai/AiStar";
import { ApiError } from "@/lib/api/client";
import { register } from "@/lib/auth/auth-service";

const ERROR_MESSAGES: Record<string, string> = {
  email_already_registered: "يوجد حساب مسجّل بهذا البريد الإلكتروني بالفعل.",
};

// Mirrors src/api/schemas/auth.py's _validate_password_complexity --
// shown up front so a user never discovers the rule only after a
// failed submit (the backend's 422 validation error isn't wrapped in
// the app's own {"error": {code, message}} shape, so apiFetch can't
// map it to a specific message -- checking here client-side instead
// gives an immediate, specific answer without waiting on that).
const PASSWORD_HINT = "8 أحرف على الأقل، تتضمن حرفًا ورقمًا.";

function passwordMeetsPolicy(value: string): boolean {
  return value.length >= 8 && /\p{L}/u.test(value) && /\d/.test(value);
}

export default function RegisterPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isRegistered, setIsRegistered] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!email.trim() || !password.trim()) {
      setError("يرجى إدخال البريد الإلكتروني وكلمة المرور.");
      return;
    }
    if (!passwordMeetsPolicy(password)) {
      setError(`كلمة المرور لا تحقق الشروط المطلوبة: ${PASSWORD_HINT}`);
      return;
    }
    setError(null);
    setIsSubmitting(true);
    try {
      await register(email.trim(), password);
      setIsRegistered(true);
    } catch (err) {
      const code = err instanceof ApiError ? err.code : null;
      setError(
        (code && ERROR_MESSAGES[code]) ??
          "تعذّر إنشاء الحساب. يرجى المحاولة مرة أخرى."
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
          {/* 2026-09-17: short, honest value-prop above the signup form
           * -- a first-time visitor previously landed on a bare form
           * with no explanation of what the product does. Deliberately
           * avoids any profit-guarantee language (matches this app's
           * existing confidence_disclaimer_ar tone throughout). */}
          <p className="text-center text-sm leading-6 text-bsr-text-secondary">
            بصيرة يحلل السوق السعودي بالذكاء الاصطناعي ويعطيك توصية واضحة
            (دخول، هدف، ووقف خسارة) مع درجة ثقة حقيقية لكل سهم. ما تحتاج خبرة
            مسبقة — القرار النهائي دائمًا لك.
          </p>
        </div>

        {isRegistered ? (
          <div className="flex flex-col items-center gap-bsr-4 text-center">
            <p className="text-sm leading-7 text-bsr-text-primary">
              تم إنشاء الحساب بنجاح. يرجى مراجعة بريدك الإلكتروني والضغط على رابط
              التأكيد لتفعيل حسابك قبل تسجيل الدخول.
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

            <label className="flex flex-col gap-bsr-1">
              <span className="text-sm text-bsr-text-secondary">كلمة المرور</span>
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
              {isSubmitting ? "جارٍ إنشاء الحساب..." : "إنشاء حساب"}
            </button>

            <p className="text-center text-sm text-bsr-text-secondary">
              لديك حساب بالفعل؟{" "}
              <Link href="/login" className="text-bsr-gold-500 hover:text-bsr-gold-400">
                تسجيل الدخول
              </Link>
            </p>
          </form>
        )}
      </div>
    </div>
  );
}
