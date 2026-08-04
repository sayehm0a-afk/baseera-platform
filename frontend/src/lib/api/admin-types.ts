/** Mirrors src/api/schemas/admin.py's SystemHealthOut/AdminDashboardSummaryOut
 * -- the subset the owner status panel (frontend-only, practical-testing
 * release) reads. Every admin route these come from requires
 * require_staff_role(StaffRole.ADMIN) server-side, so a non-staff caller
 * gets a real 403 regardless of what this page renders. */

export interface SystemHealth {
  status: string;
  details: Record<string, string>;
}

export interface AdminDashboardSummary {
  app_version: string;
  deployment_commit: string | null;
  environment: string;
  database_health: string;
  redis_health: string;
  ingestion_scheduler_running: boolean;
  market_intelligence_scheduler_running: boolean;
  market_data_provider: string | null;
  market_data_health: string | null;
  new_users_last_24h: number;
  new_users_last_7d: number;
  logins_last_24h: number;
  locked_accounts: number;
  last_scan_id: number | null;
  last_scan_status: string | null;
  last_scan_started_at: string | null;
  last_scan_finished_at: string | null;
  last_scan_symbols_requested: number | null;
  last_scan_symbols_succeeded: number | null;
  last_scan_symbols_failed: number | null;
}
