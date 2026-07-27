/** Mirrors src/api/schemas/portfolio_intelligence.py. */

export interface HoldingRequestInput {
  symbol: string;
  quantity: number;
  average_cost?: number;
}

export interface PortfolioAnalyzeRequestBody {
  portfolio_id?: number;
  name: string;
  holdings: HoldingRequestInput[];
  cash: number;
}

export interface HoldingAnalysis {
  symbol: string;
  sector: string | null;
  quantity: number;
  average_cost: number | null;
  latest_price: number | null;
  market_value: number | null;
  weight: number | null;
  unrealized_pnl: number | null;
  unrealized_pnl_pct: number | null;
  available: boolean;
  recommendation: string | null;
  confidence: number | null;
  risk_level: string | null;
  position_size: string | null;
  target_price: number | null;
  error: string | null;
}

export interface AllocationEntry {
  symbol: string;
  sector: string | null;
  quantity: number;
  market_value: number | null;
  weight: number | null;
}

export interface Allocation {
  entries: AllocationEntry[];
  cash: number;
  cash_weight: number;
  total_value: number;
}

export interface SectorExposure {
  sector: string;
  market_value: number;
  weight: number;
  holdings_count: number;
  symbols: string[];
}

export interface Concentration {
  herfindahl_index: number;
  sector_herfindahl_index: number;
  largest_position_symbol: string | null;
  largest_position_weight: number | null;
  top_3_weight: number;
  is_concentrated: boolean;
  concentration_threshold: number;
}

export interface Diversification {
  score: number;
  effective_number_of_holdings: number;
  effective_number_of_sectors: number;
  sector_count: number;
  holdings_count: number;
  narrative: string;
}

export interface CorrelationMatrix {
  symbols: string[];
  matrix: Record<string, Record<string, number>>;
  lookback_days: number;
  excluded_symbols: string[];
}

export interface RiskProfile {
  risk_score: number;
  risk_level: string;
  expected_volatility_annualized_pct: number | null;
  estimated_max_drawdown_pct: number | null;
  portfolio_beta: number | null;
  beta_unavailable_reason: string | null;
  correlation_matrix: CorrelationMatrix | null;
  excluded_from_volatility: string[];
  narrative: string;
}

export interface RebalanceAction {
  symbol: string;
  action: string;
  current_weight: number | null;
  rationale: string;
  recommendation: string | null;
  confidence: number | null;
}

export interface NewBuyOpportunity {
  symbol: string;
  sector: string | null;
  recommendation: string;
  confidence: number | null;
  final_score: number | null;
  rationale: string;
}

export interface RebalancePlan {
  rebalance_actions: RebalanceAction[];
  new_buy_opportunities: NewBuyOpportunity[];
}

export interface CashRecommendation {
  current_cash: number;
  current_cash_pct: number;
  recommended_cash_pct_min: number;
  recommended_cash_pct_max: number;
  recommended_cash_amount_min: number;
  recommended_cash_amount_max: number;
  is_within_target_band: boolean;
  rationale: string;
}

export interface OptimizationRecommendation {
  priority: number;
  title: string;
  rationale: string;
}

export interface PortfolioRecommendations {
  rebalance_actions: RebalanceAction[];
  new_buy_opportunities: NewBuyOpportunity[];
  cash_recommendation: CashRecommendation;
  optimization_recommendations: OptimizationRecommendation[];
}

export interface HealthScore {
  score: number;
  band: string;
  components: Record<string, number>;
  narrative: string;
}

export interface PortfolioNewsAlert {
  id: number;
  portfolio_id: number;
  symbol: string;
  news_event_id: number;
  alert_type: string;
  severity: string;
  message: string;
  generated_at: string;
  acknowledged_at: string | null;
}

export interface PortfolioNewsAlertList {
  alerts: PortfolioNewsAlert[];
}

export interface PortfolioAnalysis {
  portfolio_id: number;
  name: string;
  cash: number;
  total_value: number;
  generated_at: string;
  holdings: HoldingAnalysis[];
  allocation: Allocation;
  sector_exposure: SectorExposure[];
  concentration: Concentration;
  diversification: Diversification;
  risk_profile: RiskProfile;
  recommendations: PortfolioRecommendations;
  health_score: HealthScore;
}
