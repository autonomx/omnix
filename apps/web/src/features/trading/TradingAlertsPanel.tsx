import { useEffect, useState } from 'react';
import { tradingApi } from './tradingApi';
import type {
  TradingAlert,
  TradingAlertCondition,
  TradingAlertTrigger,
} from './tradingTypes';

function alertInput(alert: TradingAlert, enabled = alert.enabled) {
  return {
    instrument_id: alert.instrument_id,
    binding_id: alert.binding_id ?? null,
    condition_type: alert.condition_type,
    threshold: alert.threshold,
    enabled,
    cooldown_seconds: alert.cooldown_seconds,
  };
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
    if (!Number.isFinite(numericThreshold) || !Number.isInteger(numericCooldown) || numericCooldown < 0) {
      setStatus('error');
      return;
    }
    await runMutation(() => tradingApi.createAlert({
      alert_id: `alert-${Date.now()}`,
      instrument_id: instrumentId,
      binding_id: bindingId,
      condition_type: condition,
      threshold,
      cooldown_seconds: numericCooldown,
    }));
    setThreshold('');
  };

  const relevantAlerts = alerts.filter((alert) => alert.instrument_id === instrumentId);
  return (
    <section className="trading-alerts-panel" aria-label="Server-side Trading alerts" data-status={status}>
      <header><strong>Server alerts</strong><span>{status}</span></header>
      <p>Evaluated by the Omnix backend. Closing this page does not disable an alert.</p>
      <div className="trading-alert-form">
        <label>
          Condition
          <select value={condition} onChange={(event) => setCondition(event.target.value as TradingAlertCondition)}>
            <option value="price_above">Price crosses above</option>
            <option value="price_below">Price crosses below</option>
          </select>
        </label>
        <label>
          Threshold
          <input inputMode="decimal" value={threshold} onChange={(event) => setThreshold(event.target.value)} placeholder="Price" />
        </label>
        <label>
          Cooldown seconds
          <input inputMode="numeric" value={cooldown} onChange={(event) => setCooldown(event.target.value)} />
        </label>
        <button type="button" disabled={!threshold || status === 'saving'} onClick={() => void create()}>Create alert</button>
      </div>
      <ul className="trading-alert-list">
        {relevantAlerts.map((alert) => (
          <li key={alert.alert_id}>
            <div>
              <strong>{alert.condition_type === 'price_above' ? 'Above' : 'Below'} {alert.threshold}</strong>
              <small>Last {alert.last_observed_price ?? 'not evaluated'} · revision {alert.revision}</small>
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
              <span>{trigger.observed_price} crossed {trigger.threshold}</span>
              <time dateTime={trigger.observed_at}>{new Date(trigger.observed_at).toLocaleString()}</time>
            </li>
          ))}
        </ul>
      </details>
    </section>
  );
}
