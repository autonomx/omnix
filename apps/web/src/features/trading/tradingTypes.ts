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

export interface TradingDocument {
  record_id: string;
  record_type: string;
  revision: number;
  payload: Record<string, unknown>;
  status: string;
  updated_at?: string | null;
}
