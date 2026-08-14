export interface MarketResearchRequest {
  instrument_id: string;
  binding_id?: string | null;
  interval: string;
  bar_limit: number;
  question: string;
  selected_levels: string[];
  model?: string | null;
}

export interface ResearchSource {
  instrument_id: string;
  interval: string;
  provider: string;
  requested_binding_id?: string | null;
  resolved_binding_id: string;
  dataset_fingerprint: string;
  as_of: string;
  freshness_mode: string;
  formula_version: 'omnix-indicators-v2';
  bar_count: number;
}

export interface MarketResearchResult {
  summary: string;
  observations: string[];
  risks: string[];
  confidence: string;
  provider: string;
  model: string;
  source: ResearchSource;
  read_only: true;
  disclaimer: 'Research only. Not financial advice. No order was created or executed.';
}
