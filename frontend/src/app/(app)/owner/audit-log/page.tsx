"use client";

import { useEffect, useState } from "react";
import { RequireStaff } from "@/components/auth/RequireStaff";
import { OwnerNav } from "@/components/owner/OwnerNav";
import { EmptyState } from "@/components/patterns/EmptyState";
import { LoadingScreen } from "@/components/patterns/LoadingScreen";
import { ApiError } from "@/lib/api/client";
import { listAuditLog } from "@/lib/api/admin";
import type { AuditLogEntry } from "@/lib/api/admin-types";

const PAGE_SIZE = 50;

type PageState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; logs: AuditLogEntry[]; total: number; offset: number };

function AuditLogPageInner() {
  const [state, setState] = useState<PageState>({ status: "loading" });

  async function load(offset: number) {
    try {
      const result = await listAuditLog(PAGE_SIZE, offset);
      setState({ status: "ready", logs: result.logs, total: result.total, offset });
    } catch (error) {
      setState({
        status: "error",
        message: error instanceof ApiError ? error.message : "تعذّر تحميل سجل التدقيق.",
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
        const result = await listAuditLog(PAGE_SIZE, 0);
        if (!cancelled) setState({ status: "ready", logs: result.logs, total: result.total, offset: 0 });
      } catch (error) {
        if (!cancelled) {
          setState({
            status: "error",
            message: error instanceof ApiError ? error.message : "تعذّر تحميل سجل التدقيق.",
          });
        }
      }
    }
    initialLoad();
    return () => {
      cancelled = true;
    };
  }, []);

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
        <EmptyState title="تعذّر تحميل سجل التدقيق" description={state.message} />
      </div>
    );
  }

  const { logs, total, offset } = state;

  return (
    <div className="flex flex-col gap-bsr-4">
      <OwnerNav />
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-bsr-text-primary">سجل التدقيق (إجراءات الإدارة)</h1>
        <span className="text-sm text-bsr-text-secondary">{total.toLocaleString("ar-SA")} إجراء</span>
      </div>

      {logs.length === 0 ? (
        <EmptyState title="لا توجد إجراءات إدارية مسجّلة بعد" />
      ) : (
        <div className="overflow-x-auto rounded-bsr-lg border border-bsr-border-subtle bg-bsr-surface-raised">
          <table className="w-full min-w-[720px] text-sm">
            <thead>
              <tr className="border-b border-bsr-border-subtle text-right text-xs text-bsr-text-muted">
                <th className="p-bsr-3 font-medium">الوقت</th>
                <th className="p-bsr-3 font-medium">المُنفّذ</th>
                <th className="p-bsr-3 font-medium">الإجراء</th>
                <th className="p-bsr-3 font-medium">النوع المستهدف</th>
                <th className="p-bsr-3 font-medium">معرّف الهدف</th>
                <th className="p-bsr-3 font-medium">عنوان IP</th>
              </tr>
            </thead>
            <tbody>
              {logs.map((log) => (
                <tr key={log.id} className="border-b border-bsr-border-subtle last:border-0">
                  <td className="bsr-numeric p-bsr-3 text-bsr-text-secondary">
                    {new Date(log.created_at).toLocaleString("ar-SA", { calendar: "gregory" })}
                  </td>
                  <td className="bsr-numeric p-bsr-3 text-bsr-text-primary">{log.actor_user_id}</td>
                  <td className="p-bsr-3 text-bsr-text-primary">{log.action}</td>
                  <td className="p-bsr-3 text-bsr-text-secondary">{log.target_type}</td>
                  <td className="bsr-numeric p-bsr-3 text-bsr-text-secondary">{log.target_id ?? "—"}</td>
                  <td className="bsr-numeric p-bsr-3 text-bsr-text-secondary">{log.ip_address ?? "—"}</td>
                </tr>
              ))}
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

export default function AuditLogPage() {
  return (
    <RequireStaff>
      <AuditLogPageInner />
    </RequireStaff>
  );
}
