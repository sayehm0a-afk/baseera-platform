"use client";

import { useEffect, useState } from "react";
import { RequireStaff } from "@/components/auth/RequireStaff";
import { OwnerNav } from "@/components/owner/OwnerNav";
import { EmptyState } from "@/components/patterns/EmptyState";
import { LoadingScreen } from "@/components/patterns/LoadingScreen";
import { ApiError } from "@/lib/api/client";
import { createFeatureFlag, listFeatureFlags, updateFeatureFlag } from "@/lib/api/admin";
import type { FeatureFlag } from "@/lib/api/admin-types";

type PageState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; flags: FeatureFlag[] };

function FeatureFlagsPageInner() {
  const [state, setState] = useState<PageState>({ status: "loading" });
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [newKey, setNewKey] = useState("");
  const [newDescription, setNewDescription] = useState("");
  const [createError, setCreateError] = useState<string | null>(null);

  async function load() {
    try {
      const result = await listFeatureFlags();
      setState({ status: "ready", flags: result.feature_flags });
    } catch (error) {
      setState({
        status: "error",
        message: error instanceof ApiError ? error.message : "تعذّر تحميل مفاتيح الميزات.",
      });
    }
  }

  useEffect(() => {
    let cancelled = false;
    async function initialLoad() {
      try {
        const result = await listFeatureFlags();
        if (!cancelled) setState({ status: "ready", flags: result.feature_flags });
      } catch (error) {
        if (!cancelled) {
          setState({
            status: "error",
            message: error instanceof ApiError ? error.message : "تعذّر تحميل مفاتيح الميزات.",
          });
        }
      }
    }
    initialLoad();
    return () => {
      cancelled = true;
    };
  }, []);

  async function handleToggle(flag: FeatureFlag) {
    setBusyKey(flag.key);
    try {
      await updateFeatureFlag(flag.key, !flag.enabled);
      await load();
    } catch {
      // the list stays as-is; the toggle can be retried
    } finally {
      setBusyKey(null);
    }
  }

  async function handleCreate() {
    if (!newKey.trim()) return;
    setCreateError(null);
    setBusyKey("__new__");
    try {
      await createFeatureFlag(newKey.trim(), false, newDescription.trim() || null);
      setNewKey("");
      setNewDescription("");
      await load();
    } catch (error) {
      setCreateError(error instanceof ApiError ? error.message : "تعذّر إنشاء المفتاح.");
    } finally {
      setBusyKey(null);
    }
  }

  return (
    <div className="flex flex-col gap-bsr-4">
      <OwnerNav />
      <h1 className="text-lg font-semibold text-bsr-text-primary">مفاتيح الميزات (Feature Flags)</h1>

      <section className="flex flex-col gap-bsr-2 rounded-bsr-lg border border-bsr-border-subtle bg-bsr-surface-raised p-bsr-4">
        <h2 className="text-sm font-semibold text-bsr-text-primary">إضافة مفتاح جديد</h2>
        <div className="flex flex-wrap gap-bsr-2">
          <input
            type="text"
            value={newKey}
            onChange={(event) => setNewKey(event.target.value)}
            placeholder="مفتاح الميزة (مثال: enable_new_widget)"
            className="min-w-[220px] flex-1 rounded-bsr-sm border border-bsr-border-subtle bg-bsr-surface-overlay px-bsr-2 py-1.5 text-sm text-bsr-text-primary"
          />
          <input
            type="text"
            value={newDescription}
            onChange={(event) => setNewDescription(event.target.value)}
            placeholder="وصف مختصر (اختياري)"
            className="min-w-[220px] flex-1 rounded-bsr-sm border border-bsr-border-subtle bg-bsr-surface-overlay px-bsr-2 py-1.5 text-sm text-bsr-text-primary"
          />
          <button
            type="button"
            disabled={busyKey === "__new__" || !newKey.trim()}
            onClick={handleCreate}
            className="rounded-bsr-md bg-bsr-gold-500 px-bsr-4 py-1.5 text-sm font-semibold text-bsr-navy-950 disabled:opacity-50"
          >
            إنشاء
          </button>
        </div>
        {createError ? <p className="text-sm text-bsr-market-down">{createError}</p> : null}
      </section>

      {state.status === "loading" ? (
        <LoadingScreen />
      ) : state.status === "error" ? (
        <EmptyState title="تعذّر تحميل مفاتيح الميزات" description={state.message} />
      ) : state.flags.length === 0 ? (
        <EmptyState title="لا توجد مفاتيح ميزات بعد" />
      ) : (
        <div className="rounded-bsr-lg border border-bsr-border-subtle bg-bsr-surface-raised">
          {state.flags.map((flag) => (
            <div
              key={flag.key}
              className="flex items-center justify-between gap-bsr-3 border-b border-bsr-border-subtle p-bsr-3 last:border-0"
            >
              <div>
                <p className="bsr-numeric text-sm font-semibold text-bsr-text-primary">{flag.key}</p>
                {flag.description ? (
                  <p className="text-xs text-bsr-text-secondary">{flag.description}</p>
                ) : null}
              </div>
              <button
                type="button"
                disabled={busyKey === flag.key}
                onClick={() => handleToggle(flag)}
                className={`rounded-bsr-md px-bsr-3 py-1.5 text-xs font-semibold disabled:opacity-50 ${
                  flag.enabled
                    ? "bg-bsr-market-up/15 text-bsr-market-up"
                    : "bg-bsr-surface-overlay text-bsr-text-secondary"
                }`}
              >
                {flag.enabled ? "مُفعّل" : "معطّل"}
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function FeatureFlagsPage() {
  return (
    <RequireStaff>
      <FeatureFlagsPageInner />
    </RequireStaff>
  );
}
