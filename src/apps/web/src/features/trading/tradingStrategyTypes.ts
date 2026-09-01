export type StrategyMode = 'off' | 'shadow' | 'auto_paper';
export type FloatPreferenceMode = 'ignore' | 'score' | 'require';
export type StrategyBarInterval = '1m' | '5m';
export type HistoricalUniverseMode = 'captured_only' | 'captured_or_reconstructed' | 'reconstructed_only';
export type HistoricalUniverseOrigin = 'captured' | 'reconstructed';
export type BacktestResultQuality = 'exact' | 'mixed' | 'approximate' | 'unavailable';

export type GapPullbackConfig = {
  strategy_id: 'gap_pullback_v1';
  strategy_version: '1.0.0' | '1.1.0' | '1.2.0' | '2.0.0';
  structure_interval: StrategyBarInterval;
  execution_interval: StrategyBarInterval;
  universe_scan_time_et?: string;
  universe_discovery_source?: 'yahoo' | 'finviz';
  auto_archive_daily_universe?: boolean;
  universe_archive_grace_minutes?: number;
  universe_discovery_count?: number;
  minimum_gap_pct: string | number;
  minimum_price: string | number;
  maximum_price: string | number;
  minimum_premarket_dollar_volume: string | number;
  minimum_tod_rvol: string | number;
  allow_missing_tod_rvol: boolean;
  maximum_spread_bps: string | number;
  preferred_float_min_shares: string | number;
  preferred_float_max_shares: string | number;
  float_preference_mode: FloatPreferenceMode;
  require_catalyst_evidence: boolean;
  reject_dilution_flags: string[];
  opening_impulse_min_pct: string | number;
  pullback_min_pct: string | number;
  pullback_max_pct: string | number;
  pullback_volume_max_ratio: string | number;
  higher_low_buffer_bps: string | number;
  breakout_volume_ratio: string | number;
  pivot_left_bars: number;
  pivot_right_bars: number;
  volume_lookback_bars: number;
  require_breakout_hold: boolean;
  breakout_hold_bars: number;
  breakout_hold_tolerance_bps: string | number;
  minimum_quality_score: number;
  // Version 2.0.0-only fields. Backend defaults populate these on persisted
  // documents, but they stay optional here so literal 1.x presets remain valid.
  v2_recovery_min_pct?: string | number;
  v2_second_pullback_min_pct?: string | number;
  v2_minimum_l1_to_b1_minutes?: number;
  v2_maximum_l2_to_signal_minutes?: number;
  v2_minimum_breakout_volume_ratio?: string | number;
  v2_profit_protection_trigger_r?: string | number | null;
  v2_protected_stop_r?: string | number;
  v2_max_hold_minutes?: number;
  stop_buffer_bps: string | number;
  reward_multiple: string | number;
  exit_rsi_period: number;
  exit_rsi_threshold: string | number;
  entry_start_et: string;
  last_entry_et: string;
  intraday_learning_enabled?: boolean;
  intraday_llm_enabled?: boolean;
  intraday_llm_top_n?: number;
  intraday_llm_interval_minutes?: number;
};

export type StrategyRiskProfile = {
  risk_per_trade_pct: string | number;
  max_daily_loss_pct: string | number;
  max_open_risk_pct: string | number;
  max_positions: number;
  max_trades_per_day: number;
  max_trade_value: string | number;
  one_trade_per_symbol_per_day: boolean;
  max_spread_bps: string | number;
  entry_start_et: string;
  last_entry_et: string;
  force_flat_et: string;
  kill_switch: boolean;
};

export type TradingStrategyConfig = {
  strategy_id: string;
  account_id: string;
  strategy_kind: 'gap_pullback_v1';
  strategy_version: string;
  mode: StrategyMode;
  active_universe_id: string | null;
  config: GapPullbackConfig;
  risk: StrategyRiskProfile;
  enabled: boolean;
  archived_at?: string | null;
  archived_reason?: string | null;
  revision: number;
  created_at?: string | null;
  updated_at?: string | null;
};

export type GapperCandidate = {
  instrument_id: string;
  binding_id?: string | null;
  observed_at?: string | null;
  evidence_observed_at?: Record<string, string>;
  previous_close: string | number;
  raw_previous_close?: string | number | null;
  split_adjustment_factor?: string | number;
  corporate_action_evidence_ids?: string[];
  premarket_price: string | number;
  gap_pct: string | number;
  premarket_volume?: string | number;
  premarket_dollar_volume?: string | number;
  premarket_bar_count?: number | null;
  tod_rvol?: string | number | null;
  market_data_complete?: boolean;
  data_quality_flags?: string[];
  market_cap?: string | number | null;
  float_shares?: string | number | null;
  spread_bps?: string | number | null;
  catalyst_evidence_ids?: string[];
  dilution_flags?: string[];
  discovery_rank?: number | null;
};

export type GapperUniverse = {
  universe_id: string;
  session_date: string;
  evaluation_time: string;
  discovery_source: 'manual' | 'import' | 'scanner' | 'provider' | 'finviz';
  source_locator?: string | null;
  source_candidate_symbols?: string[];
  candidates: GapperCandidate[];
  source_fingerprint: string;
};

export type GapperUniverseFreezeInput = Omit<GapperUniverse, 'source_fingerprint'>;

export type YahooGapperDiscoveryInput = {
  universe_id: string;
  evaluation_time: string;
  count: number;
  minimum_gap_pct: string | number;
  minimum_price: string | number;
  maximum_price: string | number;
};

export type FinvizGapperDiscoveryInput = YahooGapperDiscoveryInput;

export type StrategyEvent = {
  strategy_id: string;
  event_id: string;
  run_id?: string | null;
  instrument_id: string;
  event_type: string;
  state: string;
  reason_code?: string | null;
  observed_at: string;
  idempotency_key: string;
  payload: Record<string, unknown>;
};

export type StrategyProtection = {
  strategy_id: string;
  protection_id: string;
  account_id: string;
  instrument_id: string;
  entry_order_id: string;
  exit_order_id?: string | null;
  stop_price: string | number;
  target_price: string | number;
  initial_stop_price?: string | number | null;
  initial_target_price?: string | number | null;
  mae_price?: string | number | null;
  mfe_price?: string | number | null;
  quantity: string | number;
  status: 'pending_entry' | 'active' | 'exit_submitted' | 'closed' | 'cancelled';
  trigger_reason?: string | null;
  revision: number;
};

export type V2QualificationThresholds = {
  prospective_start: string;
  minimum_matched_trades: number;
  minimum_distinct_sessions: number;
  minimum_distinct_symbols: number;
  minimum_execution_match_rate: string | number;
  minimum_expectancy_r: string | number;
  one_sided_confidence_level: string | number;
  maximum_drawdown_r: string | number;
  live_match_window_minutes: number;
};

export type V2ProspectiveQualification = {
  strategy_id: string;
  qualification_version: string;
  prospective_start: string;
  expected_profile_fingerprint: string;
  current_profile_fingerprint: string;
  profile_match: boolean;
  replay_trade_count: number;
  matched_eligible_trade_count: number;
  distinct_sessions: number;
  distinct_symbols: number;
  execution_match_rate?: string | number | null;
  expectancy_r?: string | number | null;
  one_sided_90_lcb_r?: string | number | null;
  max_drawdown_r?: string | number | null;
  thresholds: V2QualificationThresholds;
  evidence_fingerprint: string;
  prospective_economic_reviewed: boolean;
  qualified: boolean;
  reviewed: boolean;
  auto_paper_authorized: boolean;
  reason_codes: string[];
};

export type ProspectiveEconomicMetrics = {
  signal_count: number;
  matched_signal_count: number;
  matched_outcome_count: number;
  distinct_sessions: number;
  distinct_symbols: number;
  execution_match_rate?: string | number | null;
  win_count: number;
  win_rate?: string | number | null;
  expectancy_r?: string | number | null;
  one_sided_90_lcb_r?: string | number | null;
  max_drawdown_r?: string | number | null;
};

export type ProspectiveEconomicThresholds = {
  prospective_start: string;
  horizon_minutes: number;
  minimum_matched_outcomes: number;
  minimum_distinct_sessions: number;
  minimum_distinct_symbols: number;
  minimum_execution_match_rate: string | number;
  minimum_win_rate: string | number;
  minimum_expectancy_r: string | number;
  one_sided_confidence_level: string | number;
  maximum_drawdown_r: string | number;
  holdout_start: string;
  holdout_end: string;
  soak_minimum_matched_outcomes: number;
  soak_minimum_distinct_sessions: number;
  soak_minimum_distinct_symbols: number;
};

export type ProspectiveEconomicStatus = {
  strategy_id: string;
  policy_version: string;
  profile_fingerprint: string;
  thresholds: ProspectiveEconomicThresholds;
  metrics: ProspectiveEconomicMetrics;
  evidence_fingerprint: string;
  sample_ready: boolean;
  quantitative_pass: boolean;
  evaluation_recorded: boolean;
  evaluation_passed: boolean;
  evaluation_event_id?: string | null;
  sealed_holdout_unlocked: boolean;
  holdout_reviewed: boolean;
  holdout_verdict: 'UNOPENED' | 'UNDERPOWERED' | 'FAIL' | 'ROBUST' | 'GOLD';
  holdout_event_id?: string | null;
  soak_metrics: ProspectiveEconomicMetrics;
  soak_passed: boolean;
  auto_paper_reviewed: boolean;
  auto_paper_research_authorized: boolean;
  pipeline_evidence_fingerprint: string;
  reason_codes: string[];
};

export type ProspectiveEconomicHoldoutReviewInput = {
  trade_count: number;
  win_rate: string | number;
  expectancy_r: string | number;
  one_sided_90_lcb_r?: string | number | null;
  max_drawdown_r: string | number;
  artifact_ref: string;
  review_note: string;
};

export type CatalystShadowClassification = {
  classifier_id: string;
  classifier_version: string;
  catalyst_class: string;
  directional_bias: 'positive' | 'negative' | 'mixed' | 'unknown';
  novelty: 'new' | 'recycled' | 'unclear';
  dilution_risk: 'none_seen' | 'possible' | 'explicit' | 'unknown';
  confidence: number;
  evidence_ids: string[];
  rationale: string;
  shadow_only: true;
};

export type StrategyResearchReview = {
  instrument_id: string;
  status: 'reviewed' | 'missing_evidence' | 'error';
  classification?: CatalystShadowClassification | null;
  detail?: string | null;
};

export type StrategyResearchReviewResponse = {
  strategy_id: string;
  universe_id: string;
  shadow_only: true;
  reviews: StrategyResearchReview[];
};

export type StrategyCatalystCaptureResponse = {
  strategy: TradingStrategyConfig;
  universe: GapperUniverse;
  evidence_count: number;
  candidates_with_evidence: number;
  errors: Record<string, string>;
};

export type GapPullbackBacktestTrade = {
  instrument_id: string;
  discovery_rank?: number | null;
  quality_score: number;
  structure_interval: string;
  execution_interval: string;
  entry_time: string;
  exit_time: string;
  entry_price: string | number;
  exit_price: string | number;
  requested_quantity: string | number;
  entry_fill_quantity: string | number;
  stop_price: string | number;
  target_price: string | number;
  exit_reason: 'stop' | 'target' | 'rsi' | 'time' | 'eod';
  pnl_per_share: string | number;
  r_multiple: string | number;
  mfe_r: string | number;
  mae_r: string | number;
  hold_minutes: string | number;
};

export type GapPullbackBacktestSummary = {
  candidate_count: number;
  trigger_count: number;
  trade_count: number;
  win_count: number;
  loss_count: number;
  win_rate: string | number;
  expectancy_r: string | number;
  profit_factor?: string | number | null;
  average_mfe_r: string | number;
  average_mae_r: string | number;
  average_hold_minutes: string | number;
  stop_count: number;
  target_count: number;
  indicator_exit_count: number;
  risk_rejection_count: number;
  risk_rejection_reasons: Record<string, number>;
};

export type GapPullbackBacktestResult = {
  strategy_id: string;
  strategy_version: string;
  initial_cash: string | number;
  trades: GapPullbackBacktestTrade[];
  summary: GapPullbackBacktestSummary;
};

export type StrategyRangeBacktestInput = {
  start_date: string;
  end_date: string;
  initial_cash: string | number;
  assumed_spread_bps: string | number;
  max_hold_minutes: number;
  universe_scan_time_et?: string | null;
  universe_cutoff_et?: string | null;
  universe_mode?: HistoricalUniverseMode;
  reconstruction_max_age_days?: number;
  max_sessions?: number;
};

export type StrategyRangeBacktestDay = {
  session_date: string;
  status: 'backtested' | 'no_candidates' | 'missing_universe' | 'data_unavailable' | 'error';
  universe_id?: string | null;
  universe_evaluation_time?: string | null;
  universe_origin?: HistoricalUniverseOrigin | null;
  fidelity?: string | null;
  fidelity_warnings: string[];
  strategy_fidelity_adjustments: string[];
  candidate_count: number;
  starting_cash: string | number;
  ending_cash: string | number;
  pnl: string | number;
  trigger_count: number;
  trade_count: number;
  detail?: string | null;
  result?: GapPullbackBacktestResult | null;
};

export type StrategyRangeBacktestResult = {
  strategy_id: string;
  strategy_kind: string;
  strategy_version: string;
  start_date: string;
  end_date: string;
  universe_scan_time_et: string;
  universe_cutoff_et: string;
  universe_mode: HistoricalUniverseMode;
  initial_cash: string | number;
  ending_cash: string | number;
  pnl: string | number | null;
  return_pct: string | number | null;
  requested_trading_sessions: number;
  covered_sessions: number;
  exact_sessions: number;
  reconstructed_sessions: number;
  no_candidate_sessions: number;
  missing_universe_sessions: number;
  data_unavailable_sessions: number;
  error_sessions: number;
  candidate_count: number;
  trigger_count: number;
  trade_count: number;
  win_count: number;
  loss_count: number;
  expectancy_r: string | number | null;
  result_quality: BacktestResultQuality;
  days: StrategyRangeBacktestDay[];
  point_in_time_universes_required: true;
  reconstruction_is_approximate: true;
};

export type StrategyRangeBacktestAccepted = {
  run_id: string;
  status: 'queued';
  total_sessions: number;
};

export type StrategyRangeBacktestProgress = {
  run_id: string;
  strategy_id: string;
  status: 'queued' | 'running' | 'completed' | 'failed';
  completed_sessions: number;
  total_sessions: number;
  percent: number;
  current_session: string | null;
  error: string | null;
  result: StrategyRangeBacktestResult | null;
};
