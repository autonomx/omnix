export type ResearchCoverageState = 'unchecked' | 'complete' | 'failed' | 'unresolved';
export type ResearchRecommendation = 'observe_only' | 'score_only' | 'soft_gate' | 'hard_gate';

export interface HermesResearchCoverage {
  sec: ResearchCoverageState;
  company_ir: ResearchCoverageState;
  recent_news: ResearchCoverageState;
  prior_news_novelty: ResearchCoverageState;
  atm: ResearchCoverageState;
  warrants: ResearchCoverageState;
  resale_registration: ResearchCoverageState;
  convertibles: ResearchCoverageState;
}

export interface HermesResearchReport {
  report_id: string;
  report_version: number;
  instrument_id: string;
  research_started_at: string;
  research_completed_at: string | null;
  evidence_cutoff_at: string;
  omnix_known_at: string | null;
  catalyst_status: 'confirmed' | 'probable' | 'unresolved' | 'absent';
  supply_status: 'clear' | 'risk_found' | 'unresolved';
  research_status: 'complete' | 'partial' | 'timed_out' | 'failed';
  coverage: HermesResearchCoverage;
  unresolved_facts: string[];
  source_evidence_ids: string[];
  hermes_trace_id: string | null;
  planner_backend: string;
  stop_reason: string | null;
}

export interface HermesResearchEvidence {
  evidence_id: string;
  source_type: string;
  source_locator: string;
  source_authority_tier: number;
  source_published_at: string | null;
  source_available_at: string | null;
  captured_at: string;
  omnix_known_at: string | null;
  title: string | null;
  extraction_status: string;
  metadata: Record<string, unknown>;
}

export interface HermesSupplyFact {
  fact_id: string;
  supply_type: string;
  status: string;
  shares: string | number | null;
  remaining_capacity_usd: string | number | null;
  strike_price: string | number | null;
  registration_status: string | null;
  resolution_status: string;
  confidence: string | number;
  omnix_known_at: string | null;
  source_evidence_ids: string[];
}

export interface HermesResearchFactSet {
  fact_set_id: string;
  schema_version: string;
  extractor_version: string;
  generated_at: string;
  omnix_known_at: string | null;
  catalyst: {
    primary_confirmed: boolean;
    same_day: boolean;
    source_count_primary: number;
    source_count_secondary: number;
    catalyst_type: string;
    source_published_at: string | null;
    official_filing_present: boolean;
    company_release_present: boolean;
    unresolved: boolean;
  };
  supply: HermesSupplyFact[];
  supply_metrics: {
    potential_dilution_pct_float: string | number | null;
    remaining_atm_pct_market_cap: string | number | null;
    in_the_money_warrant_pct_float: string | number | null;
    registered_resale_pct_float: string | number | null;
    immediate_supply_risk: boolean | null;
    supply_resolution_status: string;
  };
  unresolved_facts: string[];
  evidence_ids: string[];
}

export interface HermesResearchFeatures {
  feature_id: string;
  projection_version: string;
  research_policy_version: string;
  decision_at: string;
  omnix_known_at: string | null;
  primary_catalyst_confirmed: boolean;
  catalyst_same_day: boolean;
  catalyst_fresh: boolean;
  catalyst_age_minutes: number | null;
  immediate_supply_risk: boolean | null;
  supply_resolution_status: string;
  research_status: string;
  unresolved_supply: boolean;
  source_authority_sufficient: boolean;
}

export interface HermesResearchAction {
  action_id: string;
  trace_id: string;
  step: number;
  operation: string;
  reason: string;
  status: string;
  result_summary: Record<string, unknown>;
  evidence_ids: string[];
  requested_at: string;
  completed_at: string | null;
  omnix_known_at: string | null;
  error_code: string | null;
}

export interface HermesShadowAnnotation {
  annotation_id: string;
  observed_at: string;
  novelty: 'new' | 'incremental' | 'recycled' | 'uncertain';
  relevance: 'high' | 'medium' | 'low' | 'uncertain';
  catalyst_class: string;
  conflict_summary: string;
  confidence: string | number;
  evidence_ids: string[];
  rationale: string;
  shadow_only: true;
}

export interface HermesResearchAudit {
  instrument_id: string;
  as_of: string;
  identity: { symbol: string; legal_name: string | null; cik: string | null; omnix_known_at: string | null } | null;
  latest_report: HermesResearchReport | null;
  report_timeline: HermesResearchReport[];
  evidence: HermesResearchEvidence[];
  fact_set: HermesResearchFactSet | null;
  features: HermesResearchFeatures | null;
  shadow: HermesShadowAnnotation | null;
  hermes_actions: HermesResearchAction[];
}

export interface HermesResearchValidation {
  validation_id: string;
  policy_version: string;
  generated_at: string;
  sample_size: number;
  exact_sample_size: number;
  feature_results: Array<{
    feature: string;
    sample_size: number;
    exact_sample_size: number;
    in_sample_effect_r: string | number | null;
    out_of_sample_effect_r: string | number | null;
    win_probability_delta: string | number | null;
    confidence_interval_low: string | number | null;
    confidence_interval_high: string | number | null;
    recommendation: ResearchRecommendation;
    reason: string;
  }>;
  promotion_allowed: boolean;
  notes: string[];
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { 'content-type': 'application/json', ...(init?.headers ?? {}) },
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof payload?.detail === 'string' ? payload.detail : JSON.stringify(payload?.detail ?? payload);
    throw new Error(`Trading research request failed (${response.status}): ${detail}`);
  }
  return payload as T;
}

export const tradingHermesResearchApi = {
  start: (instrumentId: string, strategyId: string) => requestJson<{
    report: HermesResearchReport;
    fact_set: HermesResearchFactSet;
    features: HermesResearchFeatures;
    trace_id: string;
    planner_backend: string;
    warnings: string[];
  }>('/api/trading/hermes-research/start', {
    method: 'POST',
    body: JSON.stringify({
      instrument_id: instrumentId,
      strategy_id: strategyId,
      deadline_seconds: 45,
      max_steps: 8,
      max_queries: 5,
      max_sources: 20,
      max_extracts: 8,
      run_shadow_ai: true,
    }),
  }),
  audit: (instrumentId: string, asOf?: string) => {
    const query = new URLSearchParams({ instrument_id: instrumentId });
    if (asOf) query.set('as_of', asOf);
    return requestJson<HermesResearchAudit>(`/api/trading/hermes-research/audit?${query.toString()}`);
  },
  attribution: (strategyId: string) => requestJson<Record<string, unknown>>(
    `/api/trading/hermes-research/attribution?strategy_id=${encodeURIComponent(strategyId)}`,
  ),
  validate: (strategyId: string) => requestJson<HermesResearchValidation>('/api/trading/hermes-research/validate', {
    method: 'POST',
    body: JSON.stringify({ strategy_id: strategyId, policy_version: 'trading-research-1', minimum_sample: 100, minimum_exact_sample: 50 }),
  }),
  reviewValidation: (
    sourceValidationId: string,
    approvedRecommendations: Record<string, ResearchRecommendation>,
    reviewNote: string,
  ) => requestJson<HermesResearchValidation>('/api/trading/hermes-research/validation/review', {
    method: 'POST',
    body: JSON.stringify({
      source_validation_id: sourceValidationId,
      policy_version: 'trading-research-1',
      approved_recommendations: approvedRecommendations,
      review_note: reviewNote,
      confirm_execution_authority: true,
    }),
  }),
};
