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
  read_at: string | null;
  created_at: string;
}

export interface NotificationList {
  notifications: Notification[];
  unread_count: number;
}
