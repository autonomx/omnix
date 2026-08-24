import type {
  TradingAlert,
  TradingAlertCondition,
  TradingAlertCreateInput,
  TradingAlertNotificationChannel,
  TradingAlertParameters,
  TradingAlertTriggerPolicy,
  TradingAlertUpdateInput,
} from './tradingTypes';

export const TRADING_ALERTS_CHANGED_EVENT = 'omnix:trading-alerts-changed';
export const TRADING_ALERT_TRIGGER_HIGHLIGHT_MS = 15_000;

export type TradingChartAlertState = 'active' | 'triggered' | 'disabled' | 'expired';
export type TradingAlertExpiration = 'never' | '1h' | '1d' | '1w';
export type { TradingAlertNotificationChannel, TradingAlertTriggerPolicy };

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

export function formatAlertThreshold(value: number | string): string {
  if (typeof value === 'string' && value.trim() === '') return '';
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric.toFixed(2) : String(value);
}

export function cooldownForTriggerPolicy(
  policy: TradingAlertTriggerPolicy,
  interval: string,
): number {
  if (policy === 'once') return 31_536_000;
  if (policy === 'every_time') return 0;
  const intervalSeconds: Record<string, number> = {
    '1m': 60,
    '3m': 180,
    '5m': 300,
    '15m': 900,
    '30m': 1_800,
    '1h': 3_600,
    '2h': 7_200,
    '4h': 14_400,
    '6h': 21_600,
    '8h': 28_800,
    '12h': 43_200,
    '1d': 86_400,
    '3d': 259_200,
    '1w': 604_800,
    '1mo': 2_592_000,
  };
  return intervalSeconds[interval] ?? 60;
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
  triggerPolicy?: TradingAlertTriggerPolicy;
  message?: string;
  notificationChannels?: TradingAlertNotificationChannel[];
  now?: number;
}): TradingAlertCreateInput {
  const triggerPolicy = input.triggerPolicy ?? 'every_time';
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
      message: input.message ?? '',
      notification_channels: input.notificationChannels ?? ['app', 'toast'],
      trigger_policy: triggerPolicy,
    },
    evaluation_policy: {
      interval: input.interval,
      allow_partial_bars: false,
      formula_version: 'omnix-indicators-v2',
    },
    cooldown_seconds: cooldownForTriggerPolicy(triggerPolicy, input.interval),
    expires_at: expirationTimestamp(input.expiration, input.now),
  };
}

export function chartAlertUpdateInput(
  alert: TradingAlert,
  patch: Partial<Pick<TradingAlertUpdateInput, 'threshold' | 'condition_type' | 'enabled' | 'expires_at'>> & {
    indicator_id?: TradingAlertParameters['indicator_id'];
    period?: number;
    lookback_bars?: number;
    trigger_policy?: TradingAlertTriggerPolicy;
    message?: string;
    notification_channels?: TradingAlertNotificationChannel[];
  },
): TradingAlertUpdateInput {
  const triggerPolicy = patch.trigger_policy ?? alert.parameters.trigger_policy ?? 'every_time';
  return {
    instrument_id: alert.instrument_id,
    binding_id: alert.binding_id ?? null,
    condition_type: patch.condition_type ?? alert.condition_type,
    threshold: patch.threshold ?? alert.threshold,
    parameters: {
      ...alert.parameters,
      ...(patch.indicator_id !== undefined ? { indicator_id: patch.indicator_id } : {}),
      ...(patch.period !== undefined ? { period: patch.period } : {}),
      ...(patch.lookback_bars !== undefined ? { lookback_bars: patch.lookback_bars } : {}),
      ...(patch.message !== undefined || alert.parameters.message !== undefined
        ? { message: patch.message ?? alert.parameters.message ?? '' }
        : {}),
      ...(patch.notification_channels !== undefined || alert.parameters.notification_channels !== undefined
        ? { notification_channels: patch.notification_channels ?? alert.parameters.notification_channels ?? ['app', 'toast'] }
        : {}),
      ...(patch.trigger_policy !== undefined || alert.parameters.trigger_policy !== undefined
        ? { trigger_policy: triggerPolicy }
        : {}),
    },
    evaluation_policy: { ...alert.evaluation_policy },
    enabled: patch.enabled ?? alert.enabled,
    cooldown_seconds: patch.trigger_policy
      ? cooldownForTriggerPolicy(triggerPolicy, alert.evaluation_policy.interval)
      : alert.cooldown_seconds,
    expires_at: patch.expires_at === undefined ? alert.expires_at ?? null : patch.expires_at,
  };
}
