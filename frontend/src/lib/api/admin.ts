import { apiFetch } from "./client";
import type {
  AdminDashboardSummary,
  AdminSessionList,
  AdminUser,
  AdminUserList,
  AIUsageSummary,
  Analytics,
  AnnouncementList,
  Announcement,
  AuditLogList,
  FeatureFlag,
  FeatureFlagList,
  StaffRoleValue,
  SystemHealth,
} from "./admin-types";

/** Direct, unmodified calls to the existing staff-gated
 * /api/v1/admin/system/* routes (src/api/routes/admin/system.py). */

export function getSystemHealth(): Promise<SystemHealth> {
  return apiFetch<SystemHealth>("/api/v1/admin/system/health");
}

export function getDashboardSummary(): Promise<AdminDashboardSummary> {
  return apiFetch<AdminDashboardSummary>("/api/v1/admin/system/summary");
}

/** Phase 3E: direct, unmodified calls to the remaining staff-gated
 * /api/v1/admin/* routes -- every mutation here requires ADMIN (or
 * OWNER for staff-role changes / hard delete) server-side; this layer
 * adds no logic of its own. */

export function listUsers(limit = 50, offset = 0): Promise<AdminUserList> {
  return apiFetch<AdminUserList>(`/api/v1/admin/users?limit=${limit}&offset=${offset}`);
}

export function suspendUser(userId: number): Promise<AdminUser> {
  return apiFetch<AdminUser>(`/api/v1/admin/users/${userId}/suspend`, { method: "POST" });
}

export function unsuspendUser(userId: number): Promise<AdminUser> {
  return apiFetch<AdminUser>(`/api/v1/admin/users/${userId}/unsuspend`, { method: "POST" });
}

export function setStaffRole(
  userId: number,
  isStaff: boolean,
  staffRole: StaffRoleValue | null
): Promise<AdminUser> {
  return apiFetch<AdminUser>(`/api/v1/admin/users/${userId}/staff-role`, {
    method: "POST",
    body: JSON.stringify({ is_staff: isStaff, staff_role: staffRole }),
  });
}

export function deleteUser(userId: number): Promise<{ message: string }> {
  return apiFetch<{ message: string }>(`/api/v1/admin/users/${userId}`, { method: "DELETE" });
}

export function listActiveSessions(limit = 50, offset = 0): Promise<AdminSessionList> {
  return apiFetch<AdminSessionList>(`/api/v1/admin/sessions?limit=${limit}&offset=${offset}`);
}

export function revokeSession(sessionId: number): Promise<{ message: string }> {
  return apiFetch<{ message: string }>(`/api/v1/admin/sessions/${sessionId}`, { method: "DELETE" });
}

export function revokeAllSessionsForUser(userId: number): Promise<{ message: string }> {
  return apiFetch<{ message: string }>(`/api/v1/admin/sessions/user/${userId}`, { method: "DELETE" });
}

export function listFeatureFlags(): Promise<FeatureFlagList> {
  return apiFetch<FeatureFlagList>("/api/v1/admin/feature-flags");
}

export function createFeatureFlag(
  key: string,
  enabled: boolean,
  description: string | null
): Promise<FeatureFlag> {
  return apiFetch<FeatureFlag>("/api/v1/admin/feature-flags", {
    method: "POST",
    body: JSON.stringify({ key, enabled, description }),
  });
}

export function updateFeatureFlag(key: string, enabled: boolean): Promise<FeatureFlag> {
  return apiFetch<FeatureFlag>(`/api/v1/admin/feature-flags/${encodeURIComponent(key)}`, {
    method: "PATCH",
    body: JSON.stringify({ enabled }),
  });
}

export function listAnnouncements(): Promise<AnnouncementList> {
  return apiFetch<AnnouncementList>("/api/v1/admin/announcements");
}

export function createAnnouncement(body: {
  title: string;
  body: string;
  severity: "INFO" | "WARNING" | "CRITICAL";
  starts_at: string;
  ends_at: string | null;
}): Promise<Announcement> {
  return apiFetch<Announcement>("/api/v1/admin/announcements", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function setAnnouncementActive(announcementId: number, isActive: boolean): Promise<Announcement> {
  return apiFetch<Announcement>(`/api/v1/admin/announcements/${announcementId}`, {
    method: "PATCH",
    body: JSON.stringify({ is_active: isActive }),
  });
}

export function deleteAnnouncement(announcementId: number): Promise<{ message: string }> {
  return apiFetch<{ message: string }>(`/api/v1/admin/announcements/${announcementId}`, { method: "DELETE" });
}

export function listAuditLog(limit = 50, offset = 0): Promise<AuditLogList> {
  return apiFetch<AuditLogList>(`/api/v1/admin/audit-log?limit=${limit}&offset=${offset}`);
}

export function getAIUsageSummary(): Promise<AIUsageSummary> {
  return apiFetch<AIUsageSummary>("/api/v1/admin/usage/ai");
}

export function getAnalytics(): Promise<Analytics> {
  return apiFetch<Analytics>("/api/v1/admin/analytics");
}
