import { apiFetch } from "./client";
import type { Notification, NotificationList } from "./notification-types";

/** Every function here is a direct, unmodified call to an existing
 * /api/v1/notifications/* route (src/api/routes/notifications.py) --
 * the first consumer surface for the previously write-only
 * `Notification` table (RADAR-C Phase I). */

export interface MessageResponse {
  message: string;
}

export function listNotifications(): Promise<NotificationList> {
  return apiFetch<NotificationList>("/api/v1/notifications");
}

export function markNotificationRead(
  notificationId: number
): Promise<Notification> {
  return apiFetch<Notification>(
    `/api/v1/notifications/${notificationId}/read`,
    { method: "POST" }
  );
}

export function markAllNotificationsRead(): Promise<MessageResponse> {
  return apiFetch<MessageResponse>("/api/v1/notifications/read-all", {
    method: "POST",
  });
}
