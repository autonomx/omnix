export type TradingScannerMetric = 'close' | 'percent_change' | 'volume' | 'sma' | 'ema' | 'rsi' | 'atr';
export type TradingScannerOperator = 'gt' | 'gte' | 'lt' | 'lte';
export type TradingScannerRunStatus = 'queued' | 'running' | 'completed' | 'failed' | 'cancelled' | 'timed_out';

export interface TradingScannerRule {
  rule_id: string;
  metric: TradingScannerMetric;
  operator: TradingScannerOperator;
  threshold: string;
  period: number;
  lookback_bars: number;
}

export interface TradingScannerDefinition {
  scanner_id: string;
  name: string;
  instrument_ids: string[];
  binding_ids: Record<string, string>;
  interval: string;
  history_limit: number;
  rules: TradingScannerRule[];
  max_concurrency: number;
  request_timeout_seconds: number;
  run_timeout_seconds: number;
  formula_version: 'omnix-indicators-v2';
  enabled: boolean;
  revision: number;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface TradingScannerRun {
  run_id: string;
  scanner_id: string;
  status: TradingScannerRunStatus;
  cancellation_requested: boolean;
  universe_count: number;
  completed_count: number;
  matched_count: number;
  started_at?: string | null;
  finished_at?: string | null;
  error_message?: string | null;
  definition_snapshot: Record<string, unknown>;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface TradingScannerResult {
  run_id: string;
  instrument_id: string;
  requested_binding_id?: string | null;
  resolved_binding_id: string;
  provider: string;
  dataset_fingerprint: string;
  source_as_of: string;
  formula_version: string;
  metrics: Record<string, string>;
  matched_rules: string[];
  rank: number;
  score: string;
}
