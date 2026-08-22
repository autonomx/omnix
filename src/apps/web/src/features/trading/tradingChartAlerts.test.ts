import { describe, expect, it } from 'vitest';
import {
  alertVisualState,
  chartAlertCreateInput,
  chartAlertUpdateInput,
  cooldownForTriggerPolicy,
  expirationTimestamp,
  priceConditionForThreshold,
} from './tradingChartAlerts';
import type { TradingAlert } from './tradingTypes';

const baseAlert: TradingAlert = {
  alert_id: 'chart-alert-1',
  instrument_id: 'crypto:BINANCE:spot:BTC-USDT',
  binding_id: 'binance:websocket_and_rest:crypto:BINANCE:spot:BTC-USDT',
  condition_type: 'price_above',
  threshold: '70000',
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
    interval: '2h',
    allow_partial_bars: false,
    formula_version: 'omnix-indicators-v2',
  },
  enabled: true,
  cooldown_seconds: 0,
  revision: 3,
};

describe('chart-native Trading alerts', () => {
  it('distinguishes lifecycle state from a transient trigger highlight', () => {
    const now = Date.parse('2026-08-06T07:00:00Z');
    expect(alertVisualState(baseAlert, now)).toBe('active');
    expect(alertVisualState({ ...baseAlert, last_triggered_at: '2026-08-06T06:59:50Z' }, now)).toBe('triggered');
    expect(alertVisualState({ ...baseAlert, last_triggered_at: '2026-08-06T06:59:00Z' }, now)).toBe('active');
    expect(alertVisualState({ ...baseAlert, enabled: false }, now)).toBe('disabled');
    expect(alertVisualState({ ...baseAlert, enabled: false, expires_at: '2026-08-06T06:00:00Z' }, now)).toBe('expired');
  });

  it('chooses the crossing direction from the placed chart price', () => {
    expect(priceConditionForThreshold(101, 100)).toBe('price_above');
    expect(priceConditionForThreshold(99, 100)).toBe('price_below');
  });

  it('builds a server-owned alert from the active chart contract', () => {
    const input = chartAlertCreateInput({
      alertId: 'chart-alert-2',
      instrumentId: baseAlert.instrument_id,
      bindingId: baseAlert.binding_id ?? null,
      interval: '2h',
      threshold: 71000,
      latestPrice: 70000,
      expiration: '1d',
      now: Date.parse('2026-08-06T07:00:00Z'),
    });
    expect(input.condition_type).toBe('price_above');
    expect(input.evaluation_policy?.interval).toBe('2h');
    expect(input.expires_at).toBe('2026-08-07T07:00:00.000Z');
    expect(expirationTimestamp('never')).toBeNull();
  });

  it('maps TradingView trigger choices to server-owned alert policy fields', () => {
    const input = chartAlertCreateInput({
      alertId: 'chart-alert-policy',
      instrumentId: baseAlert.instrument_id,
      bindingId: baseAlert.binding_id ?? null,
      interval: '5m',
      threshold: 71_000,
      latestPrice: 70_000,
      expiration: 'never',
      triggerPolicy: 'once_per_bar',
      message: 'Watch the breakout',
      notificationChannels: ['app', 'toast'],
    });
    expect(input.cooldown_seconds).toBe(300);
    expect(input.parameters.trigger_policy).toBe('once_per_bar');
    expect(input.parameters.message).toBe('Watch the breakout');
    expect(cooldownForTriggerPolicy('once', '1h')).toBe(31_536_000);
  });

  it('preserves policy and revision-owned fields when dragging a threshold', () => {
    const input = chartAlertUpdateInput(baseAlert, { threshold: '72000' });
    expect(input.threshold).toBe('72000');
    expect(input.evaluation_policy.interval).toBe('2h');
    expect(input.parameters).toEqual(baseAlert.parameters);
    expect(input.enabled).toBe(true);
  });

  it('persists the indicator identity when an alert is changed to RSI', () => {
    const input = chartAlertUpdateInput(baseAlert, {
      condition_type: 'indicator_cross_below',
      indicator_id: 'rsi',
      period: 14,
      threshold: '73',
    });

    expect(input.condition_type).toBe('indicator_cross_below');
    expect(input.parameters.indicator_id).toBe('rsi');
    expect(input.parameters.period).toBe(14);
  });
});
