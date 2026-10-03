import type { components } from '../../api/generated/types';
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

export type TradingScannerRun = components['schemas']['TradingScannerRun'];

export type TradingScannerResult = components['schemas']['TradingScannerResult'];
