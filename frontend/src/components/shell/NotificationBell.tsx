"use client";

import { useEffect, useRef, useState } from "react";
import {
  listNotifications,
  markAllNotificationsRead,
  markNotificationRead,
} from "@/lib/api/notifications";
import type { Notification } from "@/lib/api/notification-types";

/** The bell in TopBar -- the first consumer of the previously
 * write-only `Notification` table (RADAR-C Phase I). Loads the
 * caller's own recent notifications on mount, shows an unread-count
 * badge, and lets the user open a dropdown to read/mark them. Never
 * polls: notifications refresh on open and after an action, matching
 * this app's DB-first ("never triggers a live call on its own")
 * convention already established for Portfolio/Watchlist. */
export function NotificationBell() {
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [open, setOpen] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  function refresh() {
    listNotifications()
      .then((result) => {
        setNotifications(result.notifications);
        setUnreadCount(result.unread_count);
        setLoaded(true);
      })
      .catch(() => {
        setLoaded(true);
      });
  }

  useEffect(() => {
    refresh();
  }, []);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  function handleToggle() {
    setOpen((wasOpen) => {
      if (!wasOpen) refresh();
      return !wasOpen;
    });
  }

  function handleMarkRead(notification: Notification) {
    if (notification.read_at) return;
    markNotificationRead(notification.id)
      .then((updated) => {
        setNotifications((current) =>
          current.map((n) => (n.id === updated.id ? updated : n))
        );
        setUnreadCount((count) => Math.max(0, count - 1));
      })
      .catch(() => {
        // no-op -- the item simply stays unread, safe to retry on next open
      });
  }

  function handleMarkAllRead() {
    markAllNotificationsRead()
      .then(() => {
        const now = new Date().toISOString();
        setNotifications((current) => current.map((n) => ({ ...n, read_at: n.read_at ?? now })));
        setUnreadCount(0);
      })
      .catch(() => {
        // no-op
      });
  }

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        aria-label="التنبيهات"
        onClick={handleToggle}
        className="relative flex h-9 w-9 items-center justify-center rounded-bsr-full text-bsr-text-secondary hover:bg-bsr-surface-raised"
      >
        <svg width={18} height={18} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75} aria-hidden>
          <path d="M18 16v-5a6 6 0 1 0-12 0v5l-2 2v1h16v-1l-2-2Z" strokeLinecap="round" strokeLinejoin="round" />
          <path d="M10 21a2 2 0 0 0 4 0" strokeLinecap="round" />
        </svg>
        {unreadCount > 0 ? (
          <span className="absolute -end-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-bsr-full bg-bsr-market-down px-1 text-[10px] font-semibold text-bsr-white">
            {unreadCount > 9 ? "9+" : unreadCount}
          </span>
        ) : null}
      </button>

      {open ? (
        <div className="absolute end-0 top-full z-30 mt-bsr-2 w-80 max-w-[90vw] rounded-bsr-lg border border-bsr-border-subtle bg-bsr-surface-raised shadow-lg">
          <div className="flex items-center justify-between border-b border-bsr-border-subtle px-bsr-4 py-bsr-2">
            <span className="text-sm font-semibold text-bsr-text-primary">التنبيهات</span>
            {unreadCount > 0 ? (
              <button
                type="button"
                onClick={handleMarkAllRead}
                className="text-xs text-bsr-teal-500 hover:underline"
              >
                تعليم الكل كمقروء
              </button>
            ) : null}
          </div>

          <div className="max-h-96 overflow-y-auto">
            {!loaded ? (
              <p className="px-bsr-4 py-bsr-6 text-center text-sm text-bsr-text-secondary">جارٍ التحميل...</p>
            ) : notifications.length === 0 ? (
              <p className="px-bsr-4 py-bsr-6 text-center text-sm text-bsr-text-secondary">لا توجد تنبيهات بعد</p>
            ) : (
              <ul>
                {notifications.map((notification) => (
                  <li key={notification.id}>
                    <button
                      type="button"
                      onClick={() => handleMarkRead(notification)}
                      className={`flex w-full flex-col gap-bsr-1 border-b border-bsr-border-subtle px-bsr-4 py-bsr-3 text-start last:border-b-0 hover:bg-bsr-surface-overlay ${
                        notification.read_at ? "" : "bg-bsr-surface-overlay/40"
                      }`}
                    >
                      <span className="flex items-center gap-bsr-2">
                        {!notification.read_at ? (
                          <span className="h-1.5 w-1.5 shrink-0 rounded-bsr-full bg-bsr-gold-500" aria-hidden />
                        ) : null}
                        <span className="text-sm font-semibold text-bsr-text-primary">
                          {notification.title_ar ?? notification.title}
                        </span>
                      </span>
                      <span className="text-xs text-bsr-text-secondary">{notification.body_ar ?? notification.body}</span>
                      <span className="text-[11px] text-bsr-text-tertiary">
                        {new Date(notification.created_at).toLocaleDateString("ar-SA", { calendar: "gregory" })}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
}
