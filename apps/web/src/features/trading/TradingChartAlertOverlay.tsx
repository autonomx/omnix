import { useEffect, useMemo, useRef, useState } from 'react';
import type { TradingChartAdapter } from './chart/chartAdapter';
import type { ChartAlertPlacement } from './drawings/TradingDrawingOverlay';
import {
  alertLastTriggeredLabel,
  alertVisualState,
  chartAlertCreateInput,
  chartAlertUpdateInput,
  notifyTradingAlertsChanged,
  type TradingChartAlertState,
} from './tradingChartAlerts';
import { tradingApi } from './tradingApi';
import type { TradingAlert } from './tradingTypes';
import { useTradingAlertMutations, useTradingAlerts } from './useTradingAlerts';
import './TradingChartAlertOverlay.css';

type EditorState = {
  mode: 'create' | 'edit';
  alertId: string | null;
  x: number;
  y: number;
  threshold: string;
  condition: 'price_above' | 'price_below';
  expiresAt: string;
};

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

export function TradingChartAlertOverlay({
  adapter,
  instrumentId,
  bindingId,
  interval,
  latestPrice,
  placement,
  onPlacementConsumed,
}: {
  adapter: TradingChartAdapter | null;
  instrumentId: string;
  bindingId: string | null;
  interval: string;
  latestPrice: number;
  placement: ChartAlertPlacement | null;
  onPlacementConsumed: () => void;
}) {
  const rootRef = useRef<HTMLDivElement | null>(null);
  const alertsQuery = useTradingAlerts({ poll: true });
  const alertMutations = useTradingAlertMutations();
  const alerts = alertsQuery.data ?? [];
  const [status, setStatus] = useState<'loading' | 'ready' | 'saving' | 'conflict' | 'error'>('loading');
  const [editor, setEditor] = useState<EditorState | null>(null);
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
    setEditor({
      mode: 'create',
      alertId: null,
      x: placement.x,
      y: placement.y,
      threshold: String(placement.price),
      condition: placement.price >= latestPrice ? 'price_above' : 'price_below',
      expiresAt: '',
    });
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
      expires_at: isoDateTime(editor.expiresAt),
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
      condition: editor.condition,
      expiration: 'never',
    });
    input.expires_at = isoDateTime(editor.expiresAt);
    await runMutation(() => tradingApi.createAlert(input));
  };

  const openEditor = (alert: TradingAlert, y: number) => {
    setEditor({
      mode: 'edit',
      alertId: alert.alert_id,
      x: Math.max(8, (rootRef.current?.clientWidth ?? 320) - 260),
      y,
      threshold: alert.threshold,
      condition: alert.condition_type === 'price_below' ? 'price_below' : 'price_above',
      expiresAt: localDateTime(alert.expires_at),
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
    left: Math.max(8, Math.min(editor.x, rootRef.current.clientWidth - 250)),
    top: Math.max(8, Math.min(editor.y + 8, rootRef.current.clientHeight - 235)),
  } : undefined;

  return (
    <div ref={rootRef} className="trading-chart-alert-overlay" data-status={status}>
      <svg aria-label="Chart alert lines">
        {visibleAlerts.map((alert) => {
          const threshold = dragging?.alert.alert_id === alert.alert_id ? dragging.threshold : Number(alert.threshold);
          const y = adapter?.priceToCoordinate(threshold);
          if (y === null || y === undefined) return null;
          const state = alertVisualState(alert);
          return (
            <line
              key={alert.alert_id}
              className={`trading-alert-line state-${state}`}
              x1="0"
              x2="100%"
              y1={y}
              y2={y}
              stroke={alertColor(state)}
              onPointerDown={beginDrag(alert)}
            />
          );
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
        <form
          className="trading-chart-alert-editor"
          style={editorStyle}
          onSubmit={(event) => {
            event.preventDefault();
            void (editor.mode === 'create' ? createAlert() : saveEditor());
          }}
          onPointerDown={(event) => event.stopPropagation()}
        >
          <header><strong>{editor.mode === 'create' ? 'Add alert at price' : 'Edit chart alert'}</strong><button type="button" onClick={() => setEditor(null)} aria-label="Close alert editor">×</button></header>
          <label>Condition<select value={editor.condition} onChange={(event) => setEditor({ ...editor, condition: event.target.value as EditorState['condition'] })}><option value="price_above">Crosses above</option><option value="price_below">Crosses below</option></select></label>
          <label>Threshold<input autoFocus inputMode="decimal" value={editor.threshold} onChange={(event) => setEditor({ ...editor, threshold: event.target.value })} /></label>
          <label>Interval<input value={interval.toUpperCase()} disabled /></label>
          <label>Expires<input type="datetime-local" value={editor.expiresAt} onChange={(event) => setEditor({ ...editor, expiresAt: event.target.value })} /><small>Leave empty for no expiration.</small></label>
          <div className="trading-chart-alert-editor-actions">
            <button type="submit" disabled={status === 'saving'}>{editor.mode === 'create' ? 'Create alert' : 'Save'}</button>
            {editor.mode === 'edit' ? (() => {
              const alert = alerts.find((item) => item.alert_id === editor.alertId);
              if (!alert) return null;
              return <><button type="button" onClick={() => void runMutation(() => tradingApi.updateAlert(alert, chartAlertUpdateInput(alert, { enabled: !alert.enabled })))}>{alert.enabled ? 'Disable' : 'Enable'}</button><button type="button" className="danger" onClick={() => void runMutation(() => tradingApi.archiveAlert(alert))}>Archive</button></>;
            })() : null}
          </div>
          <small className="trading-chart-alert-editor-status">Server state: {status}</small>
        </form>
      ) : null}
    </div>
  );
}
