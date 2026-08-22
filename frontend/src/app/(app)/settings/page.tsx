"use client";

import { useState, useSyncExternalStore } from "react";
import { useRouter } from "next/navigation";
import { AiStar } from "@/components/ai/AiStar";
import {
  getSessionServerSnapshot,
  getSessionSnapshot,
  logout,
  logoutAll,
  subscribeToSession,
} from "@/lib/auth/auth-service";

function SettingsSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-bsr-lg border border-bsr-border-subtle bg-bsr-surface-raised p-bsr-4 md:p-bsr-6">
      <h2 className="mb-bsr-4 text-base font-semibold text-bsr-text-primary">{title}</h2>
      {children}
    </section>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between border-b border-bsr-border-subtle py-bsr-3 last:border-0">
      <span className="text-sm text-bsr-text-secondary">{label}</span>
      <span className="text-sm text-bsr-text-primary">{value}</span>
    </div>
  );
}

export default function SettingsPage() {
  const router = useRouter();
  const session = useSyncExternalStore(
    subscribeToSession,
    getSessionSnapshot,
    getSessionServerSnapshot
  );
  const [isSigningOut, setIsSigningOut] = useState(false);
  const [logoutError, setLogoutError] = useState<string | null>(null);

  async function handleLogout() {
    setIsSigningOut(true);
    setLogoutError(null);
    try {
      await logout();
      router.replace("/login");
    } catch {
      // logout() already clears the local session in its own `finally`
      // even when the network call fails -- the soft-lock bug was that
      // isSigningOut never reset and no message was shown, leaving both
      // buttons permanently disabled. The session is genuinely gone
      // locally either way; only the server-side revocation may not have
      // completed, so this stays recoverable rather than fatal.
      setLogoutError("تعذّر تسجيل الخروج عبر الخادم بسبب مشكلة في الاتصال. تم إنهاء الجلسة على هذا الجهاز -- يمكنك المتابعة إلى صفحة الدخول أو إعادة المحاولة.");
    } finally {
      setIsSigningOut(false);
    }
  }

  async function handleLogoutAll() {
    setIsSigningOut(true);
    setLogoutError(null);
    try {
      await logoutAll();
      router.replace("/login");
    } catch {
      setLogoutError("تعذّر تسجيل الخروج من جميع الأجهزة عبر الخادم بسبب مشكلة في الاتصال. تم إنهاء الجلسة على هذا الجهاز -- يمكنك المتابعة إلى صفحة الدخول أو إعادة المحاولة.");
    } finally {
      setIsSigningOut(false);
    }
  }

  return (
    <div className="flex flex-col gap-bsr-6">
      <div className="flex items-center gap-bsr-2">
        <AiStar size="lg" />
        <h1 className="text-lg font-semibold text-bsr-text-primary">الإعدادات</h1>
      </div>

      <SettingsSection title="الحساب">
        <Row label="البريد الإلكتروني" value={session?.email ?? "—"} />
        <Row
          label="تاريخ آخر تسجيل دخول"
          value={
            session?.last_login_at
              ? new Date(session.last_login_at).toLocaleString("ar-SA", { calendar: "gregory" })
              : "—"
          }
        />
        {logoutError ? (
          <div className="mt-bsr-3 rounded-bsr-md border border-bsr-action-sell/40 bg-bsr-action-sell/10 p-bsr-3 text-sm text-bsr-action-sell">
            <p>{logoutError}</p>
            <button
              type="button"
              onClick={() => router.replace("/login")}
              className="mt-bsr-2 text-sm font-semibold underline"
            >
              المتابعة إلى صفحة الدخول
            </button>
          </div>
        ) : null}
        <div className="flex gap-bsr-3 pt-bsr-4">
          <button
            type="button"
            disabled={isSigningOut}
            onClick={handleLogout}
            className="rounded-bsr-md border border-bsr-border-subtle px-bsr-4 py-bsr-2 text-sm text-bsr-action-sell hover:bg-bsr-surface-overlay disabled:opacity-50"
          >
            تسجيل الخروج
          </button>
          <button
            type="button"
            disabled={isSigningOut}
            onClick={handleLogoutAll}
            className="rounded-bsr-md border border-bsr-border-subtle px-bsr-4 py-bsr-2 text-sm text-bsr-text-secondary hover:bg-bsr-surface-overlay disabled:opacity-50"
          >
            تسجيل الخروج من جميع الأجهزة
          </button>
        </div>
      </SettingsSection>

      <SettingsSection title="المظهر">
        <Row label="السمة" value="داكن (الوحيدة المعتمدة)" />
      </SettingsSection>

      <SettingsSection title="اللغة">
        <Row label="العربية" value="مفعّلة (اللغة الأساسية)" />
        <div className="flex items-center justify-between border-b border-bsr-border-subtle py-bsr-3 last:border-0">
          <span className="text-sm text-bsr-text-muted">English</span>
          <span className="rounded-bsr-sm bg-bsr-surface-overlay px-bsr-2 py-0.5 text-xs text-bsr-text-muted">
            قريباً
          </span>
        </div>
      </SettingsSection>

      <SettingsSection title="مصادر البيانات">
        <p className="text-sm leading-7 text-bsr-text-secondary">
          تُعرض جميع الأسعار والتحليلات كما وردت من مزوّد البيانات المتصل. عند استخدام بيانات
          تطويرية أو تجريبية، يظهر ذلك بوضوح إلى جانب القيمة المعروضة ولا يُعرض أي رقم على أنه
          بيانات حية دون تأكيد ذلك من الخادم.
        </p>
      </SettingsSection>
    </div>
  );
}
