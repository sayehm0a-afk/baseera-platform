"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { AiStar } from "@/components/ai/AiStar";
import { login } from "@/lib/auth/temp-auth-service";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!email.trim() || !password.trim()) {
      setError("يرجى إدخال البريد الإلكتروني وكلمة المرور.");
      return;
    }
    login(email.trim());
    router.replace("/dashboard");
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
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="rounded-bsr-md border border-bsr-border-subtle bg-bsr-surface-base px-bsr-3 py-bsr-2 text-bsr-text-primary focus:border-bsr-gold-500 focus:outline-none"
            />
          </label>

          {error ? (
            <p role="alert" className="text-sm text-bsr-market-down">
              {error}
            </p>
          ) : null}

          <button
            type="submit"
            className="mt-bsr-2 rounded-bsr-md bg-bsr-gold-500 px-bsr-4 py-bsr-2 font-semibold text-bsr-navy-950 transition-colors hover:bg-bsr-gold-400"
          >
            تسجيل الدخول
          </button>
        </form>
      </div>
    </div>
  );
}
