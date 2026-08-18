export type StrategyMode = 'off' | 'shadow' | 'auto_paper';

export type GapPullbackConfig = {
  strategy_id: 'gap_pullback_v1';
  strategy_version: '1.0.0';
  minimum_gap_pct: string | number;
  minimum_price: string | number;
  maximum_price: string | number;
  minimum_premarket_dollar_volume: string | number;
  minimum_tod_rvol: string | number;
  maximum_spread_bps: string | number;
  opening_impulse_min_pct: string | number;
  pullback_min_pct: string | number;
  pullback_max_pct: string | number;
  higher_low_buffer_bps: string | number;
  breakout_volume_ratio: string | number;
  pivot_left_bars: number;
  pivot_right_bars: number;
  volume_lookback_bars: number;
  stop_buffer_bps: string | number;
  reward_multiple: string | number;
  entry_start_et: string;
  last_entry_et: string;
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
  revision: number;
  created_at?: string | null;
  updated_at?: string | null;
};

export type GapperCandidate = {
  instrument_id: string;
  binding_id?: string | null;
  previous_close: string | number;
  premarket_price: string | number;
  gap_pct: string | number;
  premarket_volume?: string | number;
  premarket_dollar_volume?: string | number;
  tod_rvol?: string | number | null;
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
  discovery_source: 'manual' | 'import' | 'scanner' | 'provider';
  candidates: GapperCandidate[];
  source_fingerprint: string;
};

export type GapperUniverseFreezeInput = Omit<GapperUniverse, 'source_fingerprint'>;

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
  quantity: string | number;
  status: 'pending_entry' | 'active' | 'exit_submitted' | 'closed' | 'cancelled';
  trigger_reason?: string | null;
  revision: number;
};
