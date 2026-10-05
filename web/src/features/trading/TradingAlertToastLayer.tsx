import { useEffect, useRef, useState } from 'react';
import { useTradingAlerts, useTradingAlertTriggers } from './useTradingAlerts';
import './TradingAlertToastLayer.css';

type Toast = { triggerId: string; title: string; message: string };

function symbol(instrumentId: string): string {
  return instrumentId.split(':').at(-1)?.replace('-', '/') ?? instrumentId;
}

export function TradingAlertToastLayer() {
  const alertsQuery = useTradingAlerts({ poll: true });
  const triggersQuery = useTradingAlertTriggers({ poll: true });
  const seen = useRef<Set<string> | null>(null);
  const [toast, setToast] = useState<Toast | null>(null);

  useEffect(() => {
    if (!triggersQuery.data) return;
    const current = new Set(triggersQuery.data.map((trigger) => trigger.trigger_id));
    if (!seen.current) {
      seen.current = current;
      return;
    }
    const trigger = triggersQuery.data.find((item) => !seen.current?.has(item.trigger_id));
    seen.current = current;
    if (!trigger) return;
    const alert = alertsQuery.data?.find((item) => item.alert_id === trigger.alert_id);
    if (alert && !(alert.parameters.notification_channels ?? ['app', 'toast']).includes('toast')) return;
    const message = alert?.parameters.message || `${symbol(trigger.instrument_id)} crossed ${trigger.threshold}`;
    setToast({ triggerId: trigger.trigger_id, title: 'Alert triggered', message });
    const timer = window.setTimeout(() => setToast((currentToast) => currentToast?.triggerId === trigger.trigger_id ? null : currentToast), 6_000);
    return () => window.clearTimeout(timer);
  }, [alertsQuery.data, triggersQuery.data]);

  if (!toast) return null;
  return <div className="trading-alert-toast-layer" role="status" aria-live="polite"><strong>{toast.title}</strong><span>{toast.message}</span><button type="button" onClick={() => setToast(null)} aria-label="Dismiss alert notification">×</button></div>;
}
