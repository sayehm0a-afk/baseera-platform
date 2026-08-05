"use client";

import { useEffect, useState } from "react";
import { RequireStaff } from "@/components/auth/RequireStaff";
import { OwnerNav } from "@/components/owner/OwnerNav";
import { EmptyState } from "@/components/patterns/EmptyState";
import { LoadingScreen } from "@/components/patterns/LoadingScreen";
import { ApiError } from "@/lib/api/client";
import { createAnnouncement, deleteAnnouncement, listAnnouncements, setAnnouncementActive } from "@/lib/api/admin";
import type { Announcement } from "@/lib/api/admin-types";

const SEVERITY_LABELS_AR: Record<Announcement["severity"], string> = {
  INFO: "معلومة",
  WARNING: "تنبيه",
  CRITICAL: "حرج",
};

const SEVERITY_COLOR: Record<Announcement["severity"], string> = {
  INFO: "text-bsr-text-secondary",
  WARNING: "text-bsr-action-watch",
  CRITICAL: "text-bsr-action-sell",
};

type PageState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; announcements: Announcement[] };

function AnnouncementsPageInner() {
  const [state, setState] = useState<PageState>({ status: "loading" });
  const [busyId, setBusyId] = useState<number | "__new__" | null>(null);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [severity, setSeverity] = useState<Announcement["severity"]>("INFO");
  const [createError, setCreateError] = useState<string | null>(null);

  async function load() {
    try {
      const result = await listAnnouncements();
      setState({ status: "ready", announcements: result.announcements });
    } catch (error) {
      setState({
        status: "error",
        message: error instanceof ApiError ? error.message : "تعذّر تحميل الإعلانات.",
      });
    }
  }

  useEffect(() => {
    let cancelled = false;
    async function initialLoad() {
      try {
        const result = await listAnnouncements();
        if (!cancelled) setState({ status: "ready", announcements: result.announcements });
      } catch (error) {
        if (!cancelled) {
          setState({
            status: "error",
            message: error instanceof ApiError ? error.message : "تعذّر تحميل الإعلانات.",
          });
        }
      }
    }
    initialLoad();
    return () => {
      cancelled = true;
    };
  }, []);

  async function handleCreate() {
    if (!title.trim() || !body.trim()) return;
    setCreateError(null);
    setBusyId("__new__");
    try {
      await createAnnouncement({
        title: title.trim(),
        body: body.trim(),
        severity,
        starts_at: new Date().toISOString(),
        ends_at: null,
      });
      setTitle("");
      setBody("");
      setSeverity("INFO");
      await load();
    } catch (error) {
      setCreateError(error instanceof ApiError ? error.message : "تعذّر إنشاء الإعلان.");
    } finally {
      setBusyId(null);
    }
  }

  async function withBusy(id: number, action: () => Promise<unknown>) {
    setBusyId(id);
    try {
      await action();
      await load();
    } catch {
      // the list stays as-is; the action can be retried
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="flex flex-col gap-bsr-4">
      <OwnerNav />
      <h1 className="text-lg font-semibold text-bsr-text-primary">الإعلانات</h1>

      <section className="flex flex-col gap-bsr-2 rounded-bsr-lg border border-bsr-border-subtle bg-bsr-surface-raised p-bsr-4">
        <h2 className="text-sm font-semibold text-bsr-text-primary">إعلان جديد</h2>
        <input
          type="text"
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          placeholder="عنوان الإعلان"
          className="rounded-bsr-sm border border-bsr-border-subtle bg-bsr-surface-overlay px-bsr-2 py-1.5 text-sm text-bsr-text-primary"
        />
        <textarea
          value={body}
          onChange={(event) => setBody(event.target.value)}
          placeholder="نص الإعلان"
          rows={3}
          className="rounded-bsr-sm border border-bsr-border-subtle bg-bsr-surface-overlay px-bsr-2 py-1.5 text-sm text-bsr-text-primary"
        />
        <div className="flex flex-wrap items-center gap-bsr-2">
          <select
            value={severity}
            onChange={(event) => setSeverity(event.target.value as Announcement["severity"])}
            className="rounded-bsr-sm border border-bsr-border-subtle bg-bsr-surface-overlay px-bsr-2 py-1.5 text-sm text-bsr-text-secondary"
          >
            <option value="INFO">معلومة</option>
            <option value="WARNING">تنبيه</option>
            <option value="CRITICAL">حرج</option>
          </select>
          <button
            type="button"
            disabled={busyId === "__new__" || !title.trim() || !body.trim()}
            onClick={handleCreate}
            className="rounded-bsr-md bg-bsr-gold-500 px-bsr-4 py-1.5 text-sm font-semibold text-bsr-navy-950 disabled:opacity-50"
          >
            نشر
          </button>
        </div>
        {createError ? <p className="text-sm text-bsr-market-down">{createError}</p> : null}
      </section>

      {state.status === "loading" ? (
        <LoadingScreen />
      ) : state.status === "error" ? (
        <EmptyState title="تعذّر تحميل الإعلانات" description={state.message} />
      ) : state.announcements.length === 0 ? (
        <EmptyState title="لا توجد إعلانات بعد" />
      ) : (
        <div className="flex flex-col gap-bsr-2">
          {state.announcements.map((announcement) => (
            <div
              key={announcement.id}
              className="rounded-bsr-lg border border-bsr-border-subtle bg-bsr-surface-raised p-bsr-4"
            >
              <div className="flex items-start justify-between gap-bsr-2">
                <div>
                  <div className="flex items-center gap-bsr-2">
                    <span className={`text-xs font-semibold ${SEVERITY_COLOR[announcement.severity]}`}>
                      {SEVERITY_LABELS_AR[announcement.severity]}
                    </span>
                    <p className="text-sm font-semibold text-bsr-text-primary">{announcement.title}</p>
                  </div>
                  <p className="mt-1 text-sm text-bsr-text-secondary">{announcement.body}</p>
                </div>
                <div className="flex shrink-0 flex-col items-end gap-bsr-2">
                  <span
                    className={`text-xs ${
                      announcement.is_active ? "text-bsr-market-up" : "text-bsr-text-muted"
                    }`}
                  >
                    {announcement.is_active ? "نشط" : "غير نشط"}
                  </span>
                  <div className="flex gap-bsr-2">
                    <button
                      type="button"
                      disabled={busyId === announcement.id}
                      onClick={() =>
                        withBusy(announcement.id, () =>
                          setAnnouncementActive(announcement.id, !announcement.is_active)
                        )
                      }
                      className="rounded-bsr-sm border border-bsr-border-subtle px-bsr-2 py-1 text-xs text-bsr-text-secondary hover:bg-bsr-surface-overlay disabled:opacity-50"
                    >
                      {announcement.is_active ? "إلغاء التفعيل" : "تفعيل"}
                    </button>
                    <button
                      type="button"
                      disabled={busyId === announcement.id}
                      onClick={() => {
                        if (window.confirm(`هل تريد حذف الإعلان "${announcement.title}"؟`)) {
                          withBusy(announcement.id, () => deleteAnnouncement(announcement.id));
                        }
                      }}
                      className="rounded-bsr-sm border border-bsr-action-sell/40 px-bsr-2 py-1 text-xs text-bsr-action-sell hover:bg-bsr-action-sell/10 disabled:opacity-50"
                    >
                      حذف
                    </button>
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function AnnouncementsPage() {
  return (
    <RequireStaff>
      <AnnouncementsPageInner />
    </RequireStaff>
  );
}
