import { useEffect, useState } from 'react';
import { tradingApi } from './tradingApi';
import type {
  TradingAlert,
  TradingAlertCondition,
  TradingAlertIndicatorId,
  TradingAlertTrigger,
} from './tradingTypes';

const conditions: Array<{ value: TradingAlertCondition; label: string }> = [
  { value: 'price_above', label: 'Price crosses above' },
  { value: 'price_below', label: 'Price crosses below' },
  { value: 'percent_change_above', label: 'Percent change crosses above' },
  { value: 'percent_change_below', label: 'Percent change crosses below' },
  { value: 'indicator_above', label: 'Indicator threshold above' },
  { value: 'indicator_below', label: 'Indicator threshold below' },
  { value: 'indicator_cross_above', label: 'Indicator crosses above' },
  { value: 'indicator_cross_below', label: 'Indicator crosses below' },
  { value: 'volume_above', label: 'Volume crosses above' },
  { value: 'volume_below', label: 'Volume crosses below' },
];

function alertInput(alert: TradingAlert, enabled = alert.enabled) {
  return {
    instrument_id: alert.instrument_id,
    binding_id: alert.binding_id ?? null,
    condition_type: alert.condition_type,
    threshold: alert.threshold,
    parameters: { ...alert.parameters },
    evaluation_policy: { ...alert.evaluation_policy },
    enabled,
    cooldown_seconds: alert.cooldown_seconds,
  };
}

function conditionLabel(condition: TradingAlertCondition): string {
  return conditions.find((item) => item.value === condition)?.label ?? condition;
}

export function TradingAlertsPanel({
  instrumentId,
  bindingId,
}: {
  instrumentId: string;
  bindingId: string | null;
}) {
  const [alerts, setAlerts] = useState<TradingAlert[]>([]);
  const [triggers, setTriggers] = useState<TradingAlertTrigger[]>([]);
  const [condition, setCondition] = useState<TradingAlertCondition>('price_above');
  const [threshold, setThreshold] = useState('');
  const [cooldown, setCooldown] = useState('0');
  const [interval, setInterval] = useState('1m');
  const [allowPartial, setAllowPartial] = useState(false);
  const [lookback, setLookback] = useState('1');
  const [indicator, setIndicator] = useState<TradingAlertIndicatorId>('rsi');
  const [period, setPeriod] = useState('14');
  const [component, setComponent] = useState<'value' | 'line' | 'signal' | 'histogram' | 'upper' | 'middle' | 'lower'>('value');
  const [status, setStatus] = useState<'loading' | 'ready' | 'saving' | 'conflict' | 'error'>('loading');

  const refresh = async () => {
    try {
      const [nextAlerts, nextTriggers] = await Promise.all([
        tradingApi.alerts(),
        tradingApi.alertTriggers(),
      ]);
      setAlerts(nextAlerts);
      setTriggers(nextTriggers);
      setStatus('ready');
    } catch {
      setStatus('error');
    }
  };

  useEffect(() => { void refresh(); }, []);

  const runMutation = async (mutation: () => Promise<unknown>) => {
    setStatus('saving');
    try {
      await mutation();
      await refresh();
    } catch (error) {
      setStatus(error instanceof Error && error.message.includes('(409)') ? 'conflict' : 'error');
    }
  };

  const create = async () => {
    const numericThreshold = Number(threshold);
    const numericCooldown = Number(cooldown);
    const numericLookback = Number(lookback);
    const numericPeriod = Number(period);
    if (
      !Number.isFinite(numericThreshold)
      || !Number.isInteger(numericCooldown)
      || numericCooldown < 0
      || !Number.isInteger(numericLookback)
      || numericLookback < 1
      || numericLookback > 500
      || !Number.isInteger(numericPeriod)
      || numericPeriod < 1
      || numericPeriod > 500
    ) {
      setStatus('error');
      return;
    }
    const isIndicator = condition.startsWith('indicator_');
    await runMutation(() => tradingApi.createAlert({
      alert_id: `alert-${Date.now()}`,
      instrument_id: instrumentId,
      binding_id: bindingId,
      condition_type: condition,
      threshold,
      parameters: {
        lookback_bars: numericLookback,
        indicator_id: isIndicator ? indicator : null,
        period: numericPeriod,
        fast_period: 12,
        slow_period: 26,
        signal_period: 9,
        component,
        anchor_bars_ago: 0,
      },
      evaluation_policy: {
        interval,
        allow_partial_bars: allowPartial,
        formula_version: 'omnix-indicators-v2',
      },
      cooldown_seconds: numericCooldown,
    }));
    setThreshold('');
  };

  const relevantAlerts = alerts.filter((alert) => alert.instrument_id === instrumentId);
  const isPercent = condition.startsWith('percent_change_');
  const isIndicator = condition.startsWith('indicator_');
  return (
    <section className="trading-alerts-panel" aria-label="Server-side Trading alerts" data-status={status}>
      <header><strong>Server alerts</strong><span>{status}</span></header>
      <p>Evaluated by the Omnix backend from normalized bars. Closing this page does not disable an alert.</p>
      <div className="trading-alert-form">
        <label>
          Condition
          <select value={condition} onChange={(event) => setCondition(event.target.value as TradingAlertCondition)}>
            {conditions.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
          </select>
        </label>
        <label>
          Threshold
          <input inputMode="decimal" value={threshold} onChange={(event) => setThreshold(event.target.value)} placeholder="Value" />
        </label>
        <label>
          Interval
          <select value={interval} onChange={(event) => setInterval(event.target.value)}>
            {['1m', '5m', '15m', '1h', '4h', '1d'].map((item) => <option key={item}>{item}</option>)}
          </select>
        </label>
        <label>
          Cooldown seconds
          <input inputMode="numeric" value={cooldown} onChange={(event) => setCooldown(event.target.value)} />
        </label>
        {isPercent ? (
          <label>
            Lookback bars
            <input inputMode="numeric" value={lookback} onChange={(event) => setLookback(event.target.value)} />
          </label>
        ) : null}
        {isIndicator ? (
          <>
            <label>
              Indicator
              <select value={indicator} onChange={(event) => setIndicator(event.target.value as TradingAlertIndicatorId)}>
                {['sma', 'ema', 'rsi', 'macd', 'bollinger', 'atr', 'vwap'].map((item) => <option key={item}>{item}</option>)}
              </select>
            </label>
            <label>
              Period
              <input inputMode="numeric" value={period} onChange={(event) => setPeriod(event.target.value)} />
            </label>
            {(indicator === 'macd' || indicator === 'bollinger') ? (
              <label>
                Component
                <select value={component} onChange={(event) => setComponent(event.target.value as typeof component)}>
                  {(indicator === 'macd' ? ['line', 'signal', 'histogram'] : ['upper', 'middle', 'lower']).map((item) => <option key={item}>{item}</option>)}
                </select>
              </label>
            ) : null}
          </>
        ) : null}
        <label className="trading-alert-partial-policy">
          <input type="checkbox" checked={allowPartial} onChange={(event) => setAllowPartial(event.target.checked)} />
          Allow partial bars
        </label>
        <button type="button" disabled={!threshold || status === 'saving'} onClick={() => void create()}>Create alert</button>
      </div>
      <ul className="trading-alert-list">
        {relevantAlerts.map((alert) => (
          <li key={alert.alert_id}>
            <div>
              <strong>{conditionLabel(alert.condition_type)} {alert.threshold}</strong>
              <small>{alert.evaluation_policy.interval} · {alert.binding_id ?? 'default feed'} · last value {alert.last_observed_value ?? 'not evaluated'} · revision {alert.revision}</small>
            </div>
            <button type="button" onClick={() => void runMutation(() => tradingApi.updateAlert(alert, alertInput(alert, !alert.enabled)))}>
              {alert.enabled ? 'Disable' : 'Enable'}
            </button>
            <button type="button" aria-label={`Archive alert ${alert.alert_id}`} onClick={() => void runMutation(() => tradingApi.archiveAlert(alert))}>×</button>
          </li>
        ))}
      </ul>
      <details>
        <summary>Recent triggers ({triggers.length})</summary>
        <ul className="trading-alert-trigger-list">
          {triggers.slice(0, 20).map((trigger) => (
            <li key={trigger.trigger_id}>
              <strong>{trigger.instrument_id}</strong>
              <span>{conditionLabel(trigger.condition_type)}: {trigger.observed_value} crossed {trigger.threshold}</span>
              <span>{trigger.provider ?? 'provider unknown'} · {trigger.binding_id ?? 'default feed'}</span>
              <time dateTime={trigger.observed_at}>Source {new Date(trigger.observed_at).toLocaleString()}</time>
              <time dateTime={trigger.evaluated_at}>Evaluated {new Date(trigger.evaluated_at).toLocaleString()}</time>
            </li>
          ))}
        </ul>
      </details>
    </section>
  );
}
