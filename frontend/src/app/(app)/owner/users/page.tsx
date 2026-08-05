"use client";

import { useEffect, useState } from "react";
import { RequireStaff } from "@/components/auth/RequireStaff";
import { OwnerNav } from "@/components/owner/OwnerNav";
import { EmptyState } from "@/components/patterns/EmptyState";
import { LoadingScreen } from "@/components/patterns/LoadingScreen";
import { ApiError } from "@/lib/api/client";
import { deleteUser, listUsers, setStaffRole, suspendUser, unsuspendUser } from "@/lib/api/admin";
import type { AdminUser, StaffRoleValue } from "@/lib/api/admin-types";

const PAGE_SIZE = 50;

const STAFF_ROLE_LABELS_AR: Record<StaffRoleValue, string> = {
  OWNER: "مالك",
  ADMIN: "مسؤول",
  SUPPORT: "دعم فني",
};

type PageState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; users: AdminUser[]; total: number; offset: number };

function UsersPageInner() {
  const [state, setState] = useState<PageState>({ status: "loading" });
  const [busyUserId, setBusyUserId] = useState<number | null>(null);

  async function load(offset: number) {
    try {
      const result = await listUsers(PAGE_SIZE, offset);
      setState({ status: "ready", users: result.users, total: result.total, offset });
    } catch (error) {
      setState({
        status: "error",
        message: error instanceof ApiError ? error.message : "تعذّر تحميل قائمة المستخدمين.",
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
        const result = await listUsers(PAGE_SIZE, 0);
        if (!cancelled) setState({ status: "ready", users: result.users, total: result.total, offset: 0 });
      } catch (error) {
        if (!cancelled) {
          setState({
            status: "error",
            message: error instanceof ApiError ? error.message : "تعذّر تحميل قائمة المستخدمين.",
          });
        }
      }
    }
    initialLoad();
    return () => {
      cancelled = true;
    };
  }, []);

  async function withBusy(userId: number, action: () => Promise<unknown>) {
    setBusyUserId(userId);
    try {
      await action();
      if (state.status === "ready") await load(state.offset);
    } catch {
      // the list stays as-is; the user can retry the action
    } finally {
      setBusyUserId(null);
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
        <EmptyState title="تعذّر تحميل قائمة المستخدمين" description={state.message} />
      </div>
    );
  }

  const { users, total, offset } = state;

  return (
    <div className="flex flex-col gap-bsr-4">
      <OwnerNav />
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-bsr-text-primary">المستخدمون</h1>
        <span className="text-sm text-bsr-text-secondary">{total.toLocaleString("ar-SA")} مستخدم</span>
      </div>

      {users.length === 0 ? (
        <EmptyState title="لا يوجد مستخدمون" />
      ) : (
        <div className="overflow-x-auto rounded-bsr-lg border border-bsr-border-subtle bg-bsr-surface-raised">
          <table className="w-full min-w-[720px] text-sm">
            <thead>
              <tr className="border-b border-bsr-border-subtle text-right text-xs text-bsr-text-muted">
                <th className="p-bsr-3 font-medium">البريد الإلكتروني</th>
                <th className="p-bsr-3 font-medium">الاسم</th>
                <th className="p-bsr-3 font-medium">الحالة</th>
                <th className="p-bsr-3 font-medium">الدور الإداري</th>
                <th className="p-bsr-3 font-medium">انضم في</th>
                <th className="p-bsr-3 font-medium">إجراءات</th>
              </tr>
            </thead>
            <tbody>
              {users.map((user) => {
                const busy = busyUserId === user.id;
                return (
                  <tr key={user.id} className="border-b border-bsr-border-subtle last:border-0">
                    <td className="p-bsr-3 text-bsr-text-primary">{user.email}</td>
                    <td className="p-bsr-3 text-bsr-text-secondary">{user.full_name ?? "—"}</td>
                    <td className="p-bsr-3">
                      <span className={user.is_active ? "text-bsr-market-up" : "text-bsr-market-down"}>
                        {user.is_active ? "نشط" : "موقوف"}
                      </span>
                    </td>
                    <td className="p-bsr-3 text-bsr-text-secondary">
                      {user.is_staff && user.staff_role ? STAFF_ROLE_LABELS_AR[user.staff_role] : "—"}
                    </td>
                    <td className="bsr-numeric p-bsr-3 text-bsr-text-secondary">
                      {new Date(user.created_at).toLocaleDateString("ar-SA")}
                    </td>
                    <td className="p-bsr-3">
                      <div className="flex flex-wrap gap-bsr-2">
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() =>
                            withBusy(user.id, () =>
                              user.is_active ? suspendUser(user.id) : unsuspendUser(user.id)
                            )
                          }
                          className="rounded-bsr-sm border border-bsr-border-subtle px-bsr-2 py-1 text-xs text-bsr-text-secondary hover:bg-bsr-surface-overlay disabled:opacity-50"
                        >
                          {user.is_active ? "إيقاف" : "إعادة تفعيل"}
                        </button>
                        <select
                          disabled={busy}
                          value={user.is_staff ? user.staff_role ?? "" : ""}
                          onChange={(event) => {
                            const value = event.target.value as StaffRoleValue | "";
                            withBusy(user.id, () =>
                              setStaffRole(user.id, value !== "", value === "" ? null : value)
                            );
                          }}
                          className="rounded-bsr-sm border border-bsr-border-subtle bg-bsr-surface-overlay px-bsr-2 py-1 text-xs text-bsr-text-secondary disabled:opacity-50"
                        >
                          <option value="">لا يوجد</option>
                          <option value="SUPPORT">دعم فني</option>
                          <option value="ADMIN">مسؤول</option>
                          <option value="OWNER">مالك</option>
                        </select>
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => {
                            if (
                              window.confirm(
                                `هل أنت متأكد من حذف الحساب ${user.email} نهائياً؟ لا يمكن التراجع عن هذا الإجراء.`
                              )
                            ) {
                              withBusy(user.id, () => deleteUser(user.id));
                            }
                          }}
                          className="rounded-bsr-sm border border-bsr-action-sell/40 px-bsr-2 py-1 text-xs text-bsr-action-sell hover:bg-bsr-action-sell/10 disabled:opacity-50"
                        >
                          حذف
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

export default function UsersPage() {
  return (
    <RequireStaff>
      <UsersPageInner />
    </RequireStaff>
  );
}
