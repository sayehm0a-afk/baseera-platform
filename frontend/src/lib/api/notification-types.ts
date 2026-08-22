/** Matches src/api/schemas/notification.py exactly. */

export type NotificationType =
  | "SYSTEM"
  | "SUBSCRIPTION"
  | "PORTFOLIO_ALERT"
  | "MARKET_ALERT"
  | "ANNOUNCEMENT";

export interface Notification {
  id: number;
  type: NotificationType;
  title: string;
  body: string;
  // Pre-launch safety fix (2026-08-22): Arabic presentation companions
  // -- null for notifications written before this field existed; render
  // with a fallback to `title`/`body` in that case.
  title_ar: string | null;
  body_ar: string | null;
  read_at: string | null;
  created_at: string;
}

export interface NotificationList {
  notifications: Notification[];
  unread_count: number;
}
