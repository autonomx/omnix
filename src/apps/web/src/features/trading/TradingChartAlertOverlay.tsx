import { useEffect, useMemo, useRef, useState } from 'react';
import type { TradingChartAdapter } from './chart/chartAdapter';
import { TradingAlertDialog, type TradingAlertEditorState } from './TradingAlertDialog';
import type { ChartAlertPlacement } from './drawings/TradingDrawingOverlay';
import {
  alertLastTriggeredLabel,
  alertVisualState,
  chartAlertCreateInput,
  chartAlertUpdateInput,
  expirationTimestamp,
  notifyTradingAlertsChanged,
  type TradingChartAlertState,
} from './tradingChartAlerts';
import { tradingApi } from './tradingApi';
import type { TradingAlert } from './tradingTypes';
import { useTradingAlertMutations, useTradingAlerts } from './useTradingAlerts';
import './TradingChartAlertOverlay.css';

type DragState = { alert: TradingAlert; threshold: number };

function localDateTime(value?: string | null): string {
  if (!value) return '';
  const date = new Date(value);
  const offset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}

function isoDateTime(value: string): string | null {
  if (!value) return null;
  const milliseconds = Date.parse(value);
  return Number.isFinite(milliseconds) ? new Date(milliseconds).toISOString() : null;
}

function alertColor(state: TradingChartAlertState): string {
  if (state === 'triggered') return '#ffd43b';
  if (state === 'disabled') return '#78899b';
  if (state === 'expired') return '#a875d4';
  return '#ff8f3d';
}

function formattedPrice(value: number): string {
  if (!Number.isFinite(value)) return '—';
  const digits = Math.abs(value) >= 1_000 ? 2 : Math.abs(value) >= 1 ? 4 : 6;
  return value.toLocaleString(undefined, { maximumFractionDigits: digits });
}

function editorDefaults(placement: ChartAlertPlacement, latestPrice: number): TradingAlertEditorState {
  return {
    mode: 'create',
    alertId: null,
    x: placement.x,
    y: placement.y,
    threshold: String(placement.price),
    condition: placement.price >= latestPrice ? 'price_above' : 'price_below',
    expiresAt: '',
    expiration: 'never',
    triggerPolicy: 'every_time',
    message: '',
    notifications: ['app', 'toast'],
    indicator: 'rsi',
    period: '14',
    lookback: '1',
  };
}

export function TradingChartAlertOverlay({
  adapter,
  instrumentId,
  bindingId,
  interval,
  latestPrice,
  symbol,
  placement,
  onPlacementConsumed,
}: {
  adapter: TradingChartAdapter | null;
  instrumentId: string;
  bindingId: string | null;
  interval: string;
  latestPrice: number;
  symbol: string;
  placement: ChartAlertPlacement | null;
  onPlacementConsumed: () => void;
}) {
  const rootRef = useRef<HTMLDivElement | null>(null);
  const alertsQuery = useTradingAlerts({ poll: true });
  const alertMutations = useTradingAlertMutations();
  const alerts = alertsQuery.data ?? [];
  const [status, setStatus] = useState<'loading' | 'ready' | 'saving' | 'conflict' | 'error'>('loading');
  const [editor, setEditor] = useState<TradingAlertEditorState | null>(null);
  const [dragging, setDragging] = useState<DragState | null>(null);
  const [, setCoordinateRevision] = useState(0);

  useEffect(() => {
    if (alertsQuery.isError) setStatus('error');
    else if (alertsQuery.isSuccess && status !== 'saving' && status !== 'conflict') setStatus('ready');
  }, [alertsQuery.isError, alertsQuery.isSuccess, status]);

  useEffect(() => {
    if (!adapter) return;
    const visibleRange = adapter.onVisibleRange(() => setCoordinateRevision((value) => value + 1));
    const resize = new ResizeObserver(() => setCoordinateRevision((value) => value + 1));
    if (rootRef.current) resize.observe(rootRef.current);
    return () => {
      visibleRange();
      resize.disconnect();
    };
  }, [adapter]);

  useEffect(() => {
    if (!placement) return;
    setEditor(editorDefaults(placement, latestPrice));
    onPlacementConsumed();
  }, [latestPrice, onPlacementConsumed, placement]);

  const visibleAlerts = useMemo(() => alerts.filter((alert) => (
    alert.instrument_id === instrumentId
    && (!alert.binding_id || !bindingId || alert.binding_id === bindingId)
    && alert.condition_type.startsWith('price_')
  )), [alerts, bindingId, instrumentId]);

  const runMutation = async (mutation: () => Promise<TradingAlert>) => {
    setStatus('saving');
    try {
      const updated = await mutation();
      alertMutations.replace(updated);
      notifyTradingAlertsChanged();
      await alertMutations.refresh();
      setEditor(null);
      setStatus('ready');
    } catch (error) {
      setStatus(error instanceof Error && error.message.includes('(409)') ? 'conflict' : 'error');
      await alertMutations.refresh();
    }
  };

  const saveEditor = async () => {
    if (!editor || editor.mode !== 'edit') return;
    const threshold = Number(editor.threshold);
    if (!Number.isFinite(threshold)) {
      setStatus('error');
      return;
    }
    const alert = alerts.find((item) => item.alert_id === editor.alertId);
    if (!alert) return;
    await runMutation(() => tradingApi.updateAlert(alert, chartAlertUpdateInput(alert, {
      threshold: String(threshold),
      condition_type: editor.condition,
      expires_at: editor.expiresAt ? isoDateTime(editor.expiresAt) : expirationTimestamp(editor.expiration),
      trigger_policy: editor.triggerPolicy,
      message: editor.message,
      notification_channels: editor.notifications,
    })));
  };

  const createAlert = async () => {
    if (!editor || editor.mode !== 'create') return;
    const threshold = Number(editor.threshold);
    if (!Number.isFinite(threshold)) {
      setStatus('error');
      return;
    }
    const input = chartAlertCreateInput({
      alertId: `chart-alert-${crypto.randomUUID()}`,
      instrumentId,
      bindingId,
      interval,
      threshold,
      latestPrice,
      condition: editor.condition === 'price_above' || editor.condition === 'price_below' ? editor.condition : undefined,
      expiration: editor.expiration,
      triggerPolicy: editor.triggerPolicy,
      message: editor.message,
      notificationChannels: editor.notifications,
    });
    input.condition_type = editor.condition;
    input.parameters = {
      ...input.parameters,
      indicator_id: editor.condition.startsWith('indicator_') ? editor.indicator : null,
      period: Number(editor.period) || 14,
      lookback_bars: Number(editor.lookback) || 1,
    };
    input.expires_at = editor.expiresAt ? isoDateTime(editor.expiresAt) : input.expires_at;
    await runMutation(() => tradingApi.createAlert(input));
  };

  const openEditor = (alert: TradingAlert, y: number) => {
    setEditor({
      mode: 'edit',
      alertId: alert.alert_id,
      x: Math.max(8, (rootRef.current?.clientWidth ?? 320) - 260),
      y,
      threshold: alert.threshold,
      condition: alert.condition_type,
      expiresAt: localDateTime(alert.expires_at),
      expiration: alert.expires_at ? '1d' : 'never',
      triggerPolicy: alert.parameters.trigger_policy
        ?? (alert.cooldown_seconds > 0 ? 'once_per_bar' : 'every_time'),
      message: alert.parameters.message ?? '',
      notifications: alert.parameters.notification_channels ?? ['app', 'toast'],
      indicator: alert.parameters.indicator_id ?? 'rsi',
      period: String(alert.parameters.period ?? 14),
      lookback: String(alert.parameters.lookback_bars ?? 1),
    });
  };

  const beginDrag = (alert: TradingAlert) => (event: React.PointerEvent<SVGLineElement>) => {
    event.preventDefault();
    event.stopPropagation();
    if (!alert.enabled || alertVisualState(alert) === 'expired' || !adapter || !rootRef.current) return;
    const bounds = rootRef.current.getBoundingClientRect();
    setDragging({ alert, threshold: Number(alert.threshold) });
    const move = (pointer: PointerEvent) => {
      const threshold = adapter.priceFromCoordinate(pointer.clientY - bounds.top);
      if (threshold !== null) setDragging({ alert, threshold });
    };
    const up = async (pointer: PointerEvent) => {
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', up);
      const threshold = adapter.priceFromCoordinate(pointer.clientY - bounds.top);
      setDragging(null);
      if (threshold === null || threshold === Number(alert.threshold)) return;
      await runMutation(() => tradingApi.updateAlert(alert, chartAlertUpdateInput(alert, { threshold: String(threshold) })));
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
  };

  const editorStyle = editor && rootRef.current ? {
    left: Math.max(8, Math.min(editor.x, rootRef.current.clientWidth - 450)),
    top: Math.max(8, Math.min(editor.y + 8, rootRef.current.clientHeight - 520)),
  } : undefined;

  return (
    <div ref={rootRef} className="trading-chart-alert-overlay" data-status={status}>
      <svg aria-label="Chart alert lines">
        {visibleAlerts.map((alert) => {
          const threshold = dragging?.alert.alert_id === alert.alert_id ? dragging.threshold : Number(alert.threshold);
          const y = adapter?.priceToCoordinate(threshold);
          if (y === null || y === undefined) return null;
          const state = alertVisualState(alert);
          return <line key={alert.alert_id} className={`trading-alert-line state-${state}`} x1="0" x2="100%" y1={y} y2={y} stroke={alertColor(state)} onPointerDown={beginDrag(alert)} />;
        })}
      </svg>

      {visibleAlerts.map((alert) => {
        const threshold = dragging?.alert.alert_id === alert.alert_id ? dragging.threshold : Number(alert.threshold);
        const y = adapter?.priceToCoordinate(threshold);
        if (y === null || y === undefined) return null;
        const state = alertVisualState(alert);
        const lastTriggered = alertLastTriggeredLabel(alert);
        return (
          <button
            key={`${alert.alert_id}:label`}
            type="button"
            className={`trading-alert-price-label state-${state}`}
            style={{ top: y }}
            title={`${state} alert · ${alert.condition_type.replace('price_', 'crosses ')} · requested feed ${alert.binding_id ?? 'default'}${lastTriggered ? ` · last triggered ${lastTriggered}` : ''} · revision ${alert.revision}`}
            onPointerDown={(event) => event.stopPropagation()}
            onClick={() => openEditor(alert, y)}
          >
            <span aria-hidden="true">⏰</span>{formattedPrice(threshold)}<small>{state}</small>
          </button>
        );
      })}

      {editor ? (
        <div style={editorStyle} className="trading-chart-alert-editor-positioner">
          <TradingAlertDialog
            editor={editor}
            symbol={symbol}
            latestPrice={latestPrice}
            status={status}
            onChange={(patch) => setEditor((current) => current ? { ...current, ...patch } : current)}
            onSubmit={() => void (editor.mode === 'create' ? createAlert() : saveEditor())}
            onClose={() => setEditor(null)}
            onToggle={editor.mode === 'edit' ? () => {
              const alert = alerts.find((item) => item.alert_id === editor.alertId);
              if (alert) void runMutation(() => tradingApi.updateAlert(alert, chartAlertUpdateInput(alert, { enabled: !alert.enabled })));
            } : undefined}
            onArchive={editor.mode === 'edit' ? () => {
              const alert = alerts.find((item) => item.alert_id === editor.alertId);
              if (alert) void runMutation(() => tradingApi.archiveAlert(alert));
            } : undefined}
          />
        </div>
      ) : null}
    </div>
  );
}
