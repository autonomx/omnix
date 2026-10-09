import { useEffect, useMemo, useRef, useState } from 'react';
import type { TradingChartAdapter } from './chart/chartAdapter';
import { chartAccessFor } from './drawings/drawingFrame';
import type { TradingDrawing } from './drawings/drawingCommands';
import { drawingMenuEntries } from './drawings/TradingDrawingOverlay';
import type { DrawingAlertLevel, DrawingInstrument } from './drawings/tools/types';
import { tradingApi } from './tradingApi';
import { chartAlertUpdateInput, notifyTradingAlertsChanged } from './tradingChartAlerts';
import type { TradingAlert } from './tradingTypes';
import { useTradingAlertMutations, useTradingAlerts } from './useTradingAlerts';

/** How long a drawing must stay still before its alerts follow it (a drag sends many moves). */
export const DRAWING_ALERT_SETTLE_MS = 600;

type Point = { time: string; price: number };

const samePoints = (left: readonly Point[] | undefined, right: readonly Point[]) => (
  left?.length === right.length && left.every((point, index) => (
    Date.parse(point.time) === Date.parse(right[index].time) && Math.abs(Number(point.price) - right[index].price) <= Math.abs(right[index].price) * 1e-9
  ))
);

/** The alerts on this chart's instrument that follow a drawing (TVP-1.4). */
export function drawingLinkedAlerts(alerts: readonly TradingAlert[], instrumentId: string): TradingAlert[] {
  return alerts.filter((alert) => alert.instrument_id === instrumentId && alert.parameters.drawing_id && alert.condition_type.startsWith('trendline_'));
}

/** The line each linked alert should have now: those whose drawing level moved, with the level's anchors. */
export function drawingAlertUpdates(
  alerts: readonly TradingAlert[],
  drawings: readonly TradingDrawing[],
  levelsOf: (drawing: TradingDrawing) => readonly DrawingAlertLevel[],
): Array<{ alert: TradingAlert; points: Point[] }> {
  return alerts.flatMap((alert) => {
    const drawing = drawings.find((item) => item.drawingId === alert.parameters.drawing_id);
    if (!drawing) return [];
    const level = levelsOf(drawing).find((item) => item.key === alert.parameters.drawing_level) ?? (alert.parameters.drawing_level ? undefined : levelsOf(drawing)[0]);
    if (!level) return [];
    const points = level.anchors.map((point) => ({ time: point.time, price: point.price }));
    const current = (alert.parameters.trendline_points ?? []).map((point) => ({ time: point.time, price: Number(point.price) }));
    return samePoints(current, points) ? [] : [{ alert, points }];
  });
}

/**
 * Keeps a drawing's line alerts on the drawing (TVP-1.4): once a drawing on this chart settles after a move, its
 * alerts take the level's new line; when a drawing on this chart is deleted, its alerts are offered for disabling.
 */
export function DrawingAlertSync({
  adapter, instrumentId, instrument, drawings,
}: {
  adapter: TradingChartAdapter | null;
  instrumentId: string;
  instrument: DrawingInstrument;
  drawings: readonly TradingDrawing[];
}) {
  const alerts = useTradingAlerts().data;
  const mutationsHook = useTradingAlertMutations();
  // A stable handle: the settle timer must not restart because the hook returned a new object.
  const mutationsRef = useRef(mutationsHook);
  useEffect(() => {
    mutationsRef.current = mutationsHook;
  });
  const linked = useMemo(() => drawingLinkedAlerts(alerts ?? [], instrumentId), [alerts, instrumentId]);
  const [orphans, setOrphans] = useState<TradingAlert[]>([]);
  const seen = useRef<Set<string>>(new Set());

  useEffect(() => {
    if (!adapter || linked.length === 0) return;
    const timer = window.setTimeout(() => {
      const access = chartAccessFor(adapter, instrument);
      const matches = adapter.drawingBarIndexMatchesBars();
      const updates = drawingAlertUpdates(linked, drawings, (drawing) => drawingMenuEntries(drawing, access, matches).drawingAlertLevels ?? []);
      for (const { alert, points } of updates) {
        const input = chartAlertUpdateInput(alert, {});
        input.parameters = { ...input.parameters, trendline_points: points.map((point) => ({ ...point, price: String(point.price) })) };
        void tradingApi.updateAlert(alert, input).then((updated) => {
          mutationsRef.current.replace(updated);
          notifyTradingAlertsChanged();
        }).catch(() => undefined);
      }
    }, DRAWING_ALERT_SETTLE_MS);
    return () => window.clearTimeout(timer);
  }, [adapter, drawings, instrument, linked]);

  // Only a deletion seen here counts: a drawing that was on this chart and is gone (another chart's drawing never is).
  useEffect(() => {
    const now = new Set(drawings.map((drawing) => drawing.drawingId));
    const gone = linked.filter((alert) => alert.enabled && seen.current.has(alert.parameters.drawing_id as string) && !now.has(alert.parameters.drawing_id as string));
    if (gone.length > 0) setOrphans((current) => [...current, ...gone.filter((alert) => !current.some((item) => item.alert_id === alert.alert_id))]);
    seen.current = now;
  }, [drawings, linked]);

  if (orphans.length === 0) return null;
  const disable = () => {
    const pending = orphans;
    setOrphans([]);
    void Promise.all(pending.map((alert) => tradingApi.updateAlert(alert, chartAlertUpdateInput(alert, { enabled: false }))))
      .then((updated) => {
        updated.forEach((alert) => mutationsRef.current.replace(alert));
        notifyTradingAlertsChanged();
      })
      .catch(() => undefined);
  };
  return (
    <div className="trading-drawing-alert-prompt" role="alertdialog" aria-label="Alerts of a deleted drawing" onPointerDown={(event) => event.stopPropagation()}>
      <span>{orphans.length === 1 ? 'An alert follows' : `${orphans.length} alerts follow`} the deleted drawing. Disable {orphans.length === 1 ? 'it' : 'them'}?</span>
      <button type="button" onClick={disable}>Disable</button>
      <button type="button" onClick={() => setOrphans([])}>Keep</button>
    </div>
  );
}
