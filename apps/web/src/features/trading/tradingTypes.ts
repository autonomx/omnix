export type AssetClass = 'crypto' | 'equity' | 'forex' | 'commodity';
export type InstrumentType = 'spot' | 'perpetual' | 'equity' | 'index';

export interface CanonicalInstrument {
  instrument_id: string;
  asset_class: AssetClass;
  instrument_type: InstrumentType;
  venue: string;
  venue_symbol: string;
  display_symbol: string;
  base_currency?: string | null;
  quote_currency?: string | null;
  exchange_timezone: string;
  session_calendar: string;
  price_scale: number;
  minimum_tick: string;
  status: 'active' | 'inactive' | 'delisted';
}

export interface ProviderPolicy {
  usage_scope: 'personal_local' | 'internal' | 'external_display' | 'licensed';
  redistribution_allowed: boolean;
  authentication_required: boolean;
  is_official_api: boolean;
  realtime_scope: string;
  delay_seconds: number;
  terms_reference: string;
  supported_asset_classes: AssetClass[];
  supported_intervals: string[];
  history_depth: string;
  rate_limit_policy: string;
}

export interface ProviderBinding {
  binding_id: string;
  instrument_id: string;
  provider: string;
  provider_symbol: string;
  feed_type: string;
  realtime_scope: string;
  delay_seconds: number;
  adjustment_capabilities: string[];
  supported_intervals: string[];
  usage_scope: ProviderPolicy['usage_scope'];
  is_official_api: boolean;
}

export interface ProviderDescriptor {
  provider: string;
  display_name: string;
  enabled: boolean;
  status: 'ready' | 'degraded' | 'unavailable';
  policy: ProviderPolicy;
  bindings: ProviderBinding[];
}

export interface MarketBar {
  instrument_id: string;
  interval: string;
  start_time: string;
  end_time: string;
  open: string;
  high: string;
  low: string;
  close: string;
  volume: string;
  is_final: boolean;
  adjustment_mode: string;
  session: string;
  provider: string;
  provider_event_id?: string | null;
  provider_sequence?: number | null;
  ingestion_revision: number;
  received_at: string;
}

export interface DatasetProvenance {
  instrument_id: string;
  requested_binding: string;
  resolved_binding: string;
  fallback_reason?: string | null;
  dataset_fingerprint: string;
  freshness_mode: 'live' | 'polled' | 'delayed' | 'cached' | 'fallback';
  as_of: string;
  received_at: string;
  delay_seconds: number;
  cached: boolean;
  history_complete: boolean;
}

export interface BarsResponse {
  instrument: CanonicalInstrument;
  binding: ProviderBinding;
  provenance: DatasetProvenance;
  interval: string;
  bars: MarketBar[];
}

export type TradingStreamMessage =
  | { type: 'bar'; bar: Omit<MarketBar, 'adjustment_mode' | 'session' | 'provider' | 'received_at'> & { binding_id: string } }
  | { type: 'error'; code: string; message: string };

export interface TradingDocument {
  record_id: string;
  record_type: string;
  revision: number;
  payload: Record<string, unknown>;
  status: string;
  updated_at?: string | null;
}

export type TradingAlertCondition =
  | 'price_above'
  | 'price_below'
  | 'percent_change_above'
  | 'percent_change_below'
  | 'indicator_above'
  | 'indicator_below'
  | 'indicator_cross_above'
  | 'indicator_cross_below'
  | 'volume_above'
  | 'volume_below';

export type TradingAlertIndicatorId = 'sma' | 'ema' | 'rsi' | 'macd' | 'bollinger' | 'atr' | 'vwap';

export interface TradingAlertParameters {
  lookback_bars: number;
  indicator_id?: TradingAlertIndicatorId | null;
  period: number;
  fast_period: number;
  slow_period: number;
  signal_period: number;
  component: 'value' | 'line' | 'signal' | 'histogram' | 'upper' | 'middle' | 'lower';
  anchor_bars_ago: number;
}

export interface TradingAlertEvaluationPolicy {
  interval: string;
  allow_partial_bars: boolean;
  formula_version: 'omnix-indicators-v2';
}

export interface TradingAlert {
  alert_id: string;
  instrument_id: string;
  binding_id?: string | null;
  condition_type: TradingAlertCondition;
  threshold: string;
  parameters: TradingAlertParameters;
  evaluation_policy: TradingAlertEvaluationPolicy;
  enabled: boolean;
  cooldown_seconds: number;
  last_observed_price?: string | null;
  last_observed_value?: string | null;
  last_triggered_at?: string | null;
  revision: number;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface TradingAlertTrigger {
  trigger_id: string;
  alert_id: string;
  instrument_id: string;
  binding_id?: string | null;
  provider?: string | null;
  observed_value: string;
  observed_price: string;
  threshold: string;
  condition_type: TradingAlertCondition;
  observed_at: string;
  evaluated_at: string;
  idempotency_key: string;
  payload: Record<string, unknown>;
}

export interface TradingAlertCreateInput {
  alert_id: string;
  instrument_id: string;
  binding_id?: string | null;
  condition_type: TradingAlertCondition;
  threshold: string;
  parameters?: Partial<TradingAlertParameters>;
  evaluation_policy?: Partial<TradingAlertEvaluationPolicy>;
  cooldown_seconds: number;
}

export interface TradingAlertUpdateInput {
  instrument_id: string;
  binding_id?: string | null;
  condition_type: TradingAlertCondition;
  threshold: string;
  parameters: TradingAlertParameters;
  evaluation_policy: TradingAlertEvaluationPolicy;
  enabled: boolean;
  cooldown_seconds: number;
}
