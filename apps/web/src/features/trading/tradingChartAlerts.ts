import type {
  TradingAlert,
  TradingAlertCondition,
  TradingAlertCreateInput,
  TradingAlertUpdateInput,
} from './tradingTypes';

export const TRADING_ALERTS_CHANGED_EVENT = 'omnix:trading-alerts-changed';
export const TRADING_ALERT_TRIGGER_HIGHLIGHT_MS = 15_000;

export type TradingChartAlertState = 'active' | 'triggered' | 'disabled' | 'expired';
export type TradingAlertExpiration = 'never' | '1h' | '1d' | '1w';

export function notifyTradingAlertsChanged(): void {
  window.dispatchEvent(new CustomEvent(TRADING_ALERTS_CHANGED_EVENT));
}

export function alertVisualState(alert: TradingAlert, now = Date.now()): TradingChartAlertState {
  if (alert.expires_at && Date.parse(alert.expires_at) <= now) return 'expired';
  if (!alert.enabled) return 'disabled';
  if (
    alert.last_triggered_at
    && now - Date.parse(alert.last_triggered_at) >= 0
    && now - Date.parse(alert.last_triggered_at) <= TRADING_ALERT_TRIGGER_HIGHLIGHT_MS
  ) return 'triggered';
  return 'active';
}

export function alertLastTriggeredLabel(alert: TradingAlert): string | null {
  return alert.last_triggered_at ? new Date(alert.last_triggered_at).toLocaleString() : null;
}

export function expirationTimestamp(expiration: TradingAlertExpiration, now = Date.now()): string | null {
  if (expiration === 'never') return null;
  const milliseconds = expiration === '1h'
    ? 60 * 60 * 1_000
    : expiration === '1d'
      ? 24 * 60 * 60 * 1_000
      : 7 * 24 * 60 * 60 * 1_000;
  return new Date(now + milliseconds).toISOString();
}

export function priceConditionForThreshold(threshold: number, latestPrice: number): TradingAlertCondition {
  return threshold >= latestPrice ? 'price_above' : 'price_below';
}

export function chartAlertCreateInput(input: {
  alertId: string;
  instrumentId: string;
  bindingId: string | null;
  interval: string;
  threshold: number;
  latestPrice: number;
  condition?: 'price_above' | 'price_below';
  expiration: TradingAlertExpiration;
  now?: number;
}): TradingAlertCreateInput {
  return {
    alert_id: input.alertId,
    instrument_id: input.instrumentId,
    binding_id: input.bindingId,
    condition_type: input.condition ?? priceConditionForThreshold(input.threshold, input.latestPrice),
    threshold: String(input.threshold),
    parameters: {
      lookback_bars: 1,
      indicator_id: null,
      period: 14,
      fast_period: 12,
      slow_period: 26,
      signal_period: 9,
      component: 'value',
      anchor_bars_ago: 0,
    },
    evaluation_policy: {
      interval: input.interval,
      allow_partial_bars: false,
      formula_version: 'omnix-indicators-v2',
    },
    cooldown_seconds: 0,
    expires_at: expirationTimestamp(input.expiration, input.now),
  };
}

export function chartAlertUpdateInput(
  alert: TradingAlert,
  patch: Partial<Pick<TradingAlertUpdateInput, 'threshold' | 'condition_type' | 'enabled' | 'expires_at'>>,
): TradingAlertUpdateInput {
  return {
    instrument_id: alert.instrument_id,
    binding_id: alert.binding_id ?? null,
    condition_type: patch.condition_type ?? alert.condition_type,
    threshold: patch.threshold ?? alert.threshold,
    parameters: { ...alert.parameters },
    evaluation_policy: { ...alert.evaluation_policy },
    enabled: patch.enabled ?? alert.enabled,
    cooldown_seconds: alert.cooldown_seconds,
    expires_at: patch.expires_at === undefined ? alert.expires_at ?? null : patch.expires_at,
  };
}
