/** Mirrors src/api/schemas/news.py. */

export interface NewsEntity {
  entity_type: string;
  symbol: string | null;
  sector: string | null;
  label: string | null;
}

export interface NewsEvent {
  id: number;
  headline: string;
  source: string;
  source_reliability_score: number | null;
  published_at: string | null;
  is_synthetic: boolean;
  category: string | null;
  sentiment_score: number | null;
  sentiment_label: string | null;
  confidence: number | null;
  explanation: string | null;
  short_term_impact: number | null;
  medium_term_impact: number | null;
  long_term_impact: number | null;
  price_impact_score: number | null;
  risk_impact_score: number | null;
  volatility_impact_score: number | null;
  duplicate_count: number;
  analyzed_at: string | null;
  analysis_model: string | null;
  entities: NewsEntity[];
}

export interface NewsFeed {
  symbol: string | null;
  total: number;
  events: NewsEvent[];
}
