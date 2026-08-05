"use client";

import { useEffect, useState } from "react";
import { RequireStaff } from "@/components/auth/RequireStaff";
import { OwnerNav } from "@/components/owner/OwnerNav";
import { EmptyState } from "@/components/patterns/EmptyState";
import { LoadingScreen } from "@/components/patterns/LoadingScreen";
import { ApiError } from "@/lib/api/client";
import { listActiveSessions, revokeAllSessionsForUser, revokeSession } from "@/lib/api/admin";
import type { AdminSession } from "@/lib/api/admin-types";

const PAGE_SIZE = 50;

type PageState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; sessions: AdminSession[]; total: number; offset: number };

function SessionsPageInner() {
  const [state, setState] = useState<PageState>({ status: "loading" });
  const [busySessionId, setBusySessionId] = useState<number | null>(null);

  async function load(offset: number) {
    try {
      const result = await listActiveSessions(PAGE_SIZE, offset);
      setState({ status: "ready", sessions: result.sessions, total: result.total, offset });
    } catch (error) {
      setState({
        status: "error",
        message: error instanceof ApiError ? error.message : "تعذّر تحميل الجلسات النشطة.",
      });
    }
  }

  function reload(offset: number) {
    setState({ status: "loading" });
    load(offset);
  }

  useEffect(() => {
    let cancelled = false;
    async function initialLoad() {
      try {
        const result = await listActiveSessions(PAGE_SIZE, 0);
        if (!cancelled) setState({ status: "ready", sessions: result.sessions, total: result.total, offset: 0 });
      } catch (error) {
        if (!cancelled) {
          setState({
            status: "error",
            message: error instanceof ApiError ? error.message : "تعذّر تحميل الجلسات النشطة.",
          });
        }
      }
    }
    initialLoad();
    return () => {
      cancelled = true;
    };
  }, []);

  async function withBusy(sessionId: number, action: () => Promise<unknown>) {
    setBusySessionId(sessionId);
    try {
      await action();
      if (state.status === "ready") await load(state.offset);
    } catch {
      // the list stays as-is; the user can retry the action
    } finally {
      setBusySessionId(null);
    }
  }

  if (state.status === "loading") {
    return (
      <div className="flex flex-col gap-bsr-4">
        <OwnerNav />
        <LoadingScreen />
      </div>
    );
  }
  if (state.status === "error") {
    return (
      <div className="flex flex-col gap-bsr-4">
        <OwnerNav />
        <EmptyState title="تعذّر تحميل الجلسات النشطة" description={state.message} />
      </div>
    );
  }

  const { sessions, total, offset } = state;

  return (
    <div className="flex flex-col gap-bsr-4">
      <OwnerNav />
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-bsr-text-primary">الجلسات النشطة</h1>
        <span className="text-sm text-bsr-text-secondary">{total.toLocaleString("ar-SA")} جلسة</span>
      </div>

      {sessions.length === 0 ? (
        <EmptyState title="لا توجد جلسات نشطة" />
      ) : (
        <div className="overflow-x-auto rounded-bsr-lg border border-bsr-border-subtle bg-bsr-surface-raised">
          <table className="w-full min-w-[720px] text-sm">
            <thead>
              <tr className="border-b border-bsr-border-subtle text-right text-xs text-bsr-text-muted">
                <th className="p-bsr-3 font-medium">معرّف المستخدم</th>
                <th className="p-bsr-3 font-medium">الجهاز</th>
                <th className="p-bsr-3 font-medium">عنوان IP</th>
                <th className="p-bsr-3 font-medium">آخر استخدام</th>
                <th className="p-bsr-3 font-medium">تنتهي في</th>
                <th className="p-bsr-3 font-medium">إجراءات</th>
              </tr>
            </thead>
            <tbody>
              {sessions.map((session) => {
                const busy = busySessionId === session.id;
                return (
                  <tr key={session.id} className="border-b border-bsr-border-subtle last:border-0">
                    <td className="bsr-numeric p-bsr-3 text-bsr-text-primary">{session.user_id}</td>
                    <td className="p-bsr-3 text-bsr-text-secondary">{session.device_label ?? "—"}</td>
                    <td className="bsr-numeric p-bsr-3 text-bsr-text-secondary">{session.ip_address ?? "—"}</td>
                    <td className="bsr-numeric p-bsr-3 text-bsr-text-secondary">
                      {new Date(session.last_used_at).toLocaleString("ar-SA")}
                    </td>
                    <td className="bsr-numeric p-bsr-3 text-bsr-text-secondary">
                      {new Date(session.expires_at).toLocaleString("ar-SA")}
                    </td>
                    <td className="p-bsr-3">
                      <div className="flex flex-wrap gap-bsr-2">
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => withBusy(session.id, () => revokeSession(session.id))}
                          className="rounded-bsr-sm border border-bsr-action-sell/40 px-bsr-2 py-1 text-xs text-bsr-action-sell hover:bg-bsr-action-sell/10 disabled:opacity-50"
                        >
                          إلغاء هذه الجلسة
                        </button>
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => {
                            if (
                              window.confirm(
                                `هل تريد إلغاء جميع جلسات المستخدم ${session.user_id}؟`
                              )
                            ) {
                              withBusy(session.id, () => revokeAllSessionsForUser(session.user_id));
                            }
                          }}
                          className="rounded-bsr-sm border border-bsr-border-subtle px-bsr-2 py-1 text-xs text-bsr-text-secondary hover:bg-bsr-surface-overlay disabled:opacity-50"
                        >
                          إلغاء كل جلسات المستخدم
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <div className="flex items-center justify-between">
        <button
          type="button"
          disabled={offset === 0}
          onClick={() => reload(Math.max(0, offset - PAGE_SIZE))}
          className="rounded-bsr-md border border-bsr-border-subtle px-bsr-3 py-1.5 text-sm text-bsr-text-secondary disabled:opacity-40"
        >
          السابق
        </button>
        <span className="text-xs text-bsr-text-muted">
          {offset + 1}–{Math.min(offset + PAGE_SIZE, total)} من {total}
        </span>
        <button
          type="button"
          disabled={offset + PAGE_SIZE >= total}
          onClick={() => reload(offset + PAGE_SIZE)}
          className="rounded-bsr-md border border-bsr-border-subtle px-bsr-3 py-1.5 text-sm text-bsr-text-secondary disabled:opacity-40"
        >
          التالي
        </button>
      </div>
    </div>
  );
}

export default function SessionsPage() {
  return (
    <RequireStaff>
      <SessionsPageInner />
    </RequireStaff>
  );
}
