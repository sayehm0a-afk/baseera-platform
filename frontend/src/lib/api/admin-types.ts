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

  /** Phase 1 Decision Engine V2 additions. */
  last_scan_published_count: number | null;
  last_scan_watch_only_count: number | null;
  last_scan_rejected_count: number | null;
  last_scan_insufficient_data_count: number | null;
  last_scan_latest_error: string | null;
  decision_engine_version: string;
  market_status: string;
  market_status_label_ar: string;
  strict_real_data_enforced: boolean;
  scan_lock_active: boolean;
}

/** Phase 3E: mirrors the remaining src/api/schemas/admin.py shapes the
 * new admin screens read/write -- every route these come from is
 * staff-gated server-side (ADMIN for most, OWNER for the two
 * genuinely irreversible/privilege-escalating actions: hard delete
 * and staff-role changes), so these types exist purely for UI
 * ergonomics, not as a security boundary. */

export type StaffRoleValue = "OWNER" | "ADMIN" | "SUPPORT";

export interface AdminUser {
  id: number;
  email: string;
  full_name: string | null;
  is_email_verified: boolean;
  is_active: boolean;
  is_staff: boolean;
  staff_role: StaffRoleValue | null;
  created_at: string;
  last_login_at: string | null;
}

export interface AdminUserList {
  total: number;
  users: AdminUser[];
}

export interface AdminSession {
  id: number;
  user_id: number;
  device_label: string | null;
  ip_address: string | null;
  issued_at: string;
  last_used_at: string;
  expires_at: string;
}

export interface AdminSessionList {
  total: number;
  sessions: AdminSession[];
}

export interface Announcement {
  id: number;
  title: string;
  body: string;
  severity: "INFO" | "WARNING" | "CRITICAL";
  starts_at: string;
  ends_at: string | null;
  is_active: boolean;
  created_by_user_id: number;
  created_at: string;
}

export interface AnnouncementList {
  announcements: Announcement[];
}

export interface FeatureFlag {
  key: string;
  enabled: boolean;
  description: string | null;
}

export interface FeatureFlagList {
  feature_flags: FeatureFlag[];
}

export interface AuditLogEntry {
  id: number;
  actor_user_id: number;
  action: string;
  target_type: string;
  target_id: number | null;
  details_json: Record<string, unknown> | null;
  ip_address: string | null;
  created_at: string;
}

export interface AuditLogList {
  total: number;
  logs: AuditLogEntry[];
}

export interface AIUsageSummary {
  total_requests: number;
  success_count: number;
  failed_count: number;
  timeout_count: number;
  total_tokens: number;
  estimated_cost_usd: number;
  by_feature: Record<string, number>;
}

export interface Analytics {
  total_users: number;
  users_by_staff_role: Record<string, number>;
  subscriptions_by_status: Record<string, number>;
  subscriptions_by_plan: Record<string, number>;
  total_portfolios: number;
  total_backtest_runs: number;
}

export interface DecisionCount {
  decision: string;
  count: number;
}

export interface ConfidenceBucketCount {
  bucket_label: string;
  count: number;
}

export interface RiskCount {
  risk_level: string | null;
  count: number;
}

export interface TopOpportunity {
  symbol: string;
  company_name_ar: string | null;
  sector_ar: string | null;
  decision: string;
  decision_label_ar: string;
  confidence_score: number;
  risk_level: string | null;
  decision_timestamp: string;
}

export interface RejectedOpportunity {
  symbol: string;
  company_name_ar: string | null;
  sector_ar: string | null;
  decision: string;
  failed_gate_names: string[];
  decision_timestamp: string;
}

export interface RejectionReasonCount {
  gate_name: string;
  fail_count: number;
}

export interface SectorRanking {
  sector_ar: string | null;
  symbols_evaluated: number;
  average_confidence: number | null;
  buy_candidate_count: number;
}

/** GET /api/v1/admin/market-intelligence/decision-intelligence -- real,
 * SQL-backed statistics over each symbol's most recent Decision Engine
 * V2 snapshot within the reporting window. */
export interface DecisionIntelligence {
  generated_at: string;
  window_hours: number;
  total_symbols_evaluated: number;
  decision_distribution: DecisionCount[];
  confidence_buckets: ConfidenceBucketCount[];
  risk_distribution: RiskCount[];
  top_opportunities: TopOpportunity[];
  rejected_opportunities: RejectedOpportunity[];
  rejection_reason_counts: RejectionReasonCount[];
  sector_ranking: SectorRanking[];
}

/** AI Multi-Agent Investment Committee -- GET
 * /api/v1/admin/investment-committee/*. Every field is a direct read
 * of the real, persisted CommitteeConsensus/CommitteeAgentOpinion rows
 * (see src.ai_evolution.committee) -- no client-side computation. */
export type AgentStanceValue = "BULLISH" | "BEARISH" | "NEUTRAL" | "UNAVAILABLE";

export interface CommitteeSessionSummary {
  session_id: number;
  decision_v2_snapshot_id: number;
  symbol: string;
  company_name_ar: string | null;
  decision: string;
  decision_label_ar: string;
  final_decision: string;
  final_confidence: number;
  agreement_pct: number;
  disagreement_pct: number;
  disagreement_score: number;
  most_optimistic_agent: string | null;
  most_conservative_agent: string | null;
  created_at: string;
}

export interface CommitteeSessionList {
  generated_at: string;
  total_sessions: number;
  sessions: CommitteeSessionSummary[];
}

export interface CommitteeAgentOpinionDetail {
  agent_name: string;
  role: string;
  stance: AgentStanceValue;
  confidence: number;
  reasoning: string;
  evidence: string[];
  rejection_reasons: string[];
  used_llm: boolean;
}

export interface RejectedAlternativeDetail {
  agent_name: string;
  role: string;
  stance: AgentStanceValue;
  confidence: number;
  reasoning: string;
  rejection_reason: string;
}

export interface CommitteeSessionDetail {
  session_id: number;
  decision_v2_snapshot_id: number;
  symbol: string;
  company_name_ar: string | null;
  decision: string;
  decision_label_ar: string;
  decision_timestamp: string;
  final_decision: string;
  final_confidence: number;
  participant_count: number;
  directional_count: number;
  agreement_pct: number;
  disagreement_pct: number;
  disagreement_score: number;
  most_optimistic_agent: string | null;
  most_optimistic_stance: string | null;
  most_conservative_agent: string | null;
  most_conservative_stance: string | null;
  consensus_reasoning_ar: string;
  weighted_votes: Record<string, number>;
  rejected_alternatives: RejectedAlternativeDetail[];
  opinions: CommitteeAgentOpinionDetail[];
  created_at: string;
}

export interface CommitteeStats {
  generated_at: string;
  window_hours: number;
  total_sessions: number;
  average_agreement_pct: number | null;
  average_disagreement_score: number | null;
  final_decision_distribution: Record<string, number>;
  most_optimistic_agent_counts: Record<string, number>;
  most_conservative_agent_counts: Record<string, number>;
}
