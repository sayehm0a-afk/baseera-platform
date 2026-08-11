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

export type StaffRoleValue = "OWNER" | "ADMIN" | "ANALYST" | "SUPPORT";

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

/** OWNER-only performance dashboard for the personal day-trading
 * product (CONT Phase 3) -- GET
 * /api/v1/admin/ai-evolution/personal-performance. Distinct from the
 * public /api/v1/recommendations/history/stats track record: this
 * diagnostic view is deliberately staff-role-gated (OWNER, not just
 * ADMIN) server-side. Every field is a direct read of already-computed
 * aggregates; `null`/empty fields paired with
 * `insufficient_data_message_ar` mean "not enough data," never a
 * fabricated figure. */
export interface GroupPerformance {
  group: string;
  sample_size: number;
  win_rate: number | null;
}

export interface PersonalPerformanceDashboard {
  generated_at: string;
  evaluation_horizon_days: number;

  total_decisions_issued: number;
  decision_distribution: Record<string, number>;
  entry_status_distribution: Record<string, number>;
  market_risk_state_distribution: Record<string, number>;
  sector_distribution: Record<string, number>;

  outcome_sample_size: number;
  terminal_outcome_sample_size: number;
  status_counts: Record<string, number>;
  target_1_hit_rate: number | null;
  target_2_hit_rate: number | null;
  target_3_hit_rate: number | null;
  stop_loss_hit_rate: number | null;
  expired_count: number;
  unresolved_count: number;
  average_max_favorable_excursion_pct: number | null;
  average_max_adverse_excursion_pct: number | null;
  average_realized_return_pct: number | null;

  calibration_by_bucket: { overall_error: number; buckets: unknown[] } | null;
  calibration_by_type: Record<string, Record<string, unknown>>;
  calibration_by_holding_period: Record<string, Record<string, unknown>>;
  calibration_by_sector: Record<string, Record<string, unknown>>;
  market_risk_state_calibration_unavailable_ar: string;

  strongest_groups: GroupPerformance[];
  weakest_groups: GroupPerformance[];

  small_sample_warning: boolean;
  insufficient_data_message_ar: string | null;
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

/** Mirrors src/api/schemas/market_intelligence.py's MarketCoverageOut and
 * its nested types -- real, SQL-backed evidence of how much of the Saudi
 * market Basirah actually tracks/scans/can recommend from right now. */

export interface UniverseBucketCount {
  bucket: string | null;
  count: number;
}

export interface IngestionJobStatus {
  job_name: string;
  status: string | null;
  symbols_requested: number;
  symbols_succeeded: number;
  symbols_failed: number;
  rows_upserted: number;
  retry_count: number;
  started_at: string | null;
  finished_at: string | null;
  duration_seconds: number | null;
  error_summary: string | null;
}

export interface MarketScanRunSummary {
  id: number;
  status: string;
  symbols_requested: number;
  symbols_succeeded: number;
  symbols_skipped: number;
  symbols_failed: number;
  error_summary: string | null;
  started_at: string | null;
  finished_at: string | null;
  duration_seconds: number | null;
  created_at: string;
}

export interface SectorCoverage {
  sector: string | null;
  total_stocks: number;
  active_stocks: number;
  stocks_with_price_history: number;
  coverage_pct: number | null;
}

export interface DbConsistency {
  active_stocks_missing_instrument_bucket: number;
  active_stocks_missing_sector: number;
  active_stocks_missing_exchange: number;
  inactive_stocks_missing_exclusion_reason: number;
  active_stocks_with_exclusion_reason_set: number;
}

export interface PipelineStage {
  stage: string;
  output_count: number;
  relative_to: number;
  dropped: number;
  reason: string;
}

export interface MarketCoverage {
  generated_at: string;
  total_stocks: number;
  active_stocks: number;
  inactive_stocks: number;
  stocks_with_price_history: number;
  stocks_without_price_history: number;
  instrument_bucket_counts: UniverseBucketCount[];
  ingestion_auto_discover_enabled: boolean;
  ingestion_configured_seed_symbols: number;
  latest_ingestion_runs: IngestionJobStatus[];
  latest_scan_run: MarketScanRunSummary | null;
  coverage_pct: number | null;
  main_market_stocks: number;
  nomu_market_stocks: number;
  unclassified_market_segment_stocks: number;
  excluded_instrument_counts: UniverseBucketCount[];
  total_excluded_non_equity: number;
  stocks_with_fundamentals: number;
  stocks_without_fundamentals: number;
  stocks_with_dividends: number;
  stocks_without_dividends: number;
  sector_coverage: SectorCoverage[];
  latest_scan_symbols_entering_decision_engine: number;
  latest_scan_recommendations_generated: number;
  db_consistency: DbConsistency;
  pipeline_funnel: PipelineStage[];
}

export interface FullDiscoveryTrigger {
  triggered_at: string;
  accepted: boolean;
  message: string;
  job_names: string[];
}

/** Mirrors src/api/schemas/admin.py's AdminSubscriptionOut/AdminSubscriptionListOut
 * -- src.domain.models.Subscription rows, real trial/paid lifecycle state.
 * No payment gateway is integrated in this codebase yet (src/billing/provider.py
 * is the seam for one) -- this page must never imply real payment processing. */
export interface AdminSubscription {
  id: number;
  user_id: number;
  plan: string;
  status: string;
  trial_ends_at: string | null;
  current_period_start: string | null;
  current_period_end: string | null;
  cancel_at_period_end: boolean;
}

export interface AdminSubscriptionList {
  total: number;
  subscriptions: AdminSubscription[];
}
