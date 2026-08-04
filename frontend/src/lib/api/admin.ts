import { apiFetch } from "./client";
import type { AdminDashboardSummary, SystemHealth } from "./admin-types";

/** Direct, unmodified calls to the existing staff-gated
 * /api/v1/admin/system/* routes (src/api/routes/admin/system.py). */

export function getSystemHealth(): Promise<SystemHealth> {
  return apiFetch<SystemHealth>("/api/v1/admin/system/health");
}

export function getDashboardSummary(): Promise<AdminDashboardSummary> {
  return apiFetch<AdminDashboardSummary>("/api/v1/admin/system/summary");
}
