import { useQuery } from '@tanstack/react-query';
import { useCallback, useEffect, useRef, useState } from 'react';
import { TradingChartAlertOverlay } from './TradingChartAlertOverlay';
import { tradingApi } from './tradingApi';
import { TradingChartAdapter, type TradingChartType } from './chart/chartAdapter';
import type { TradingChartSynchronization } from './chart/chartSynchronization';
import { TradingDrawingOverlay, type ChartAlertPlacement } from './drawings/TradingDrawingOverlay';
import './drawings/TradingDrawingOverlay.css';
import { useTradingDrawings } from './drawings/useTradingDrawings';
import type { CoreIndicatorInstance } from './indicators/coreIndicators';
import { TradingIndicatorScheduler } from './indicators/indicatorScheduler';
import { tradingStreamHub, type TradingStreamStatus } from './streaming/tradingStreamHub';
import { useTradingStore } from './tradingStore';
import type { MarketBar, TradingStreamMessage } from './tradingTypes';

const ranges = [
  { label: '1D', days: 1 },
  { label: '5D', days: 5 },
  { label: '1M', days: 30 },
  { label: '3M', days: 90 },
  { label: '6M', days: 180 },
  { label: 'YTD', days: 250 },
  { label: '1Y', days: 365 },
  { label: '5Y', days: 1_825 },
  { label: 'All', days: null },
] as const;

function normalizeStreamBar(
  message: Extract<TradingStreamMessage, { type: 'bar' }>,
  provider: string,
): MarketBar {
  return {
    instrument_id: message.bar.instrument_id,
    interval: message.bar.interval,
    start_time: message.bar.start_time,
    end_time: message.bar.end_time,
    open: message.bar.open,
    high: message.bar.high,
    low: message.bar.low,
    close: message.bar.close,
    volume: message.bar.volume,
    is_final: message.bar.is_final,
    adjustment_mode: 'raw',
    session: '24x7',
    provider,
    provider_event_id: message.bar.provider_event_id,
    provider_sequence: message.bar.provider_sequence,
    ingestion_revision: message.bar.ingestion_revision,
    received_at: new Date().toISOString(),
  };
}

function downloadDataUrl(dataUrl: string, filename: string): void {
  const anchor = document.createElement('a');
  anchor.href = dataUrl;
  anchor.download = filename;
  anchor.click();
}

function price(value?: string | null): string {
  const parsed = Number(value ?? 0);
  if (!Number.isFinite(parsed)) return String(value ?? '—');
  const digits = Math.abs(parsed) >= 1_000 ? 2 : Math.abs(parsed) >= 1 ? 4 : 6;
  return parsed.toLocaleString(undefined, { maximumFractionDigits: digits });
}

function intervalMinutes(interval: string): number {
  const match = interval.match(/^(\d+)(m|h|d|w)$/i);
  if (!match) return 1_440;
  const amount = Number(match[1]);
  const unit = match[2].toLowerCase();
  if (unit === 'm') return amount;
  if (unit === 'h') return amount * 60;
  if (unit === 'w') return amount * 10_080;
  return amount * 1_440;
}

export function TradingChartPanel({
  chartId,
  instrumentId,
  bindingId,
  interval,
  chartType,
  indicators,
  active,
  onActivate,
  synchronization,
}: {
  chartId: string;
  instrumentId: string;
  bindingId: string | null;
  interval: string;
  chartType: TradingChartType;
  indicators: CoreIndicatorInstance[];
  active: boolean;
  onActivate: () => void;
  synchronization: TradingChartSynchronization;
}) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const adapterRef = useRef<TradingChartAdapter | null>(null);
  const barsRef = useRef<MarketBar[]>([]);
  const indicatorsRef = useRef<CoreIndicatorInstance[]>(indicators);
  const indicatorSchedulerRef = useRef<TradingIndicatorScheduler | null>(null);
  const indicatorTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const drawingTool = useTradingStore((state) => state.drawingTool);
  const drawingSnapMode = useTradingStore((state) => state.drawingSnapMode);
  const drawings = useTradingDrawings(instrumentId);
  const selectedDrawing = drawings.state.drawings.find((drawing) => drawing.drawingId === drawings.state.selectedId) ?? null;
  const [adapter, setAdapter] = useState<TradingChartAdapter | null>(null);
  const [streamStatus, setStreamStatus] = useState<TradingStreamStatus>('connecting');
  const [streamError, setStreamError] = useState<string | null>(null);
  const [indicatorError, setIndicatorError] = useState<string | null>(null);
  const [alertPlacement, setAlertPlacement] = useState<ChartAlertPlacement | null>(null);
  const clearAlertPlacement = useCallback(() => setAlertPlacement(null), []);
  const scheduleIndicators = useCallback((delay = 0) => {
    if (indicatorTimerRef.current) clearTimeout(indicatorTimerRef.current);
    indicatorTimerRef.current = setTimeout(() => {
      indicatorTimerRef.current = null;
      const scheduler = indicatorSchedulerRef.current;
      const targetAdapter = adapterRef.current;
      if (!scheduler || !targetAdapter) return;
      void scheduler.calculate(barsRef.current, indicatorsRef.current)
        .then((outputs) => {
          if (outputs && adapterRef.current === targetAdapter) {
            targetAdapter.setIndicatorOutputs(outputs);
            setIndicatorError(null);
          }
        })
        .catch((error) => setIndicatorError(error instanceof Error ? error.message : String(error)));
    }, delay);
  }, []);
  const chartQuery = useQuery({
    queryKey: ['trading', 'bars', instrumentId, bindingId, interval],
    queryFn: () => tradingApi.bars(instrumentId, interval, 1_000, bindingId),
    enabled: Boolean(instrumentId),
    staleTime: 15_000,
  });

  useEffect(() => {
    if (!hostRef.current) return;
    const next = new TradingChartAdapter(hostRef.current, chartType);
    const scheduler = new TradingIndicatorScheduler();
    adapterRef.current = next;
    indicatorSchedulerRef.current = scheduler;
    setAdapter(next);
    const unregister = synchronization.register(chartId, next);
    return () => {
      unregister();
      if (indicatorTimerRef.current) clearTimeout(indicatorTimerRef.current);
      indicatorTimerRef.current = null;
      scheduler.destroy();
      next.destroy();
      indicatorSchedulerRef.current = null;
      adapterRef.current = null;
      setAdapter(null);
    };
  }, [chartId, synchronization]);

  useEffect(() => {
    const bars = chartQuery.data?.bars ?? [];
    barsRef.current = bars;
    adapterRef.current?.setBars(bars);
    scheduleIndicators();
  }, [chartQuery.data, scheduleIndicators]);

  useEffect(() => {
    adapterRef.current?.setChartType(chartType, barsRef.current);
  }, [chartType]);

  useEffect(() => {
    indicatorsRef.current = indicators;
    scheduleIndicators();
  }, [indicators, scheduleIndicators]);

  useEffect(() => {
    const resolved = chartQuery.data?.binding;
    if (!instrumentId || !resolved) return;
    setStreamError(null);
    if (resolved.feed_type !== 'websocket_and_rest') {
      setStreamStatus('polling');
      const poll = window.setInterval(() => void chartQuery.refetch(), 30_000);
      return () => window.clearInterval(poll);
    }
    return tradingStreamHub.subscribe(
      chartId,
      instrumentId,
      interval,
      (message) => {
        if (message.type === 'error') {
          setStreamError(message.message);
          return;
        }
        const bar = normalizeStreamBar(message, resolved.provider);
        if (adapterRef.current?.updateBar(bar)) {
          const index = barsRef.current.findIndex((item) => item.start_time === bar.start_time);
          if (index >= 0) barsRef.current[index] = bar;
          else barsRef.current = [...barsRef.current, bar];
          scheduleIndicators(bar.is_final ? 0 : 100);
        }
      },
      (status) => {
        setStreamStatus(status);
        if (status === 'closed' || status === 'error') void chartQuery.refetch();
      },
      resolved.binding_id,
    );
  }, [chartId, instrumentId, interval, chartQuery.data?.binding.binding_id, scheduleIndicators]);

  const provenance = chartQuery.data?.provenance;
  const resolvedBinding = chartQuery.data?.binding;
  const bars = chartQuery.data?.bars ?? [];
  const latest = bars[bars.length - 1];
  const previous = bars[bars.length - 2];
  const latestClose = Number(latest?.close ?? 0);
  const previousClose = Number(previous?.close ?? latest?.open ?? 0);
  const change = latestClose - previousClose;
  const changePercent = previousClose === 0 ? 0 : change / previousClose * 100;
  const direction = change < 0 ? 'negative' : 'positive';

  const showRange = (days: number | null) => {
    const chart = adapterRef.current?.api();
    if (!chart) return;
    if (days === null) {
      chart.timeScale().fitContent();
      return;
    }
    const total = barsRef.current.length;
    if (total === 0) return;
    const requested = Math.max(1, Math.ceil(days * 1_440 / intervalMinutes(interval)));
    const count = Math.min(total, requested);
    chart.timeScale().setVisibleLogicalRange({
      from: Math.max(-0.5, total - count - 0.5),
      to: total - 0.5,
    });
  };

  return (
    <article
      className={`trading-chart-panel${active ? ' active' : ''}`}
      data-chart-id={chartId}
      data-stream-status={streamStatus}
      onPointerDown={onActivate}
      aria-label={`${chartId}${active ? ', active chart' : ''}`}
    >
      <header className="trading-chart-header">
        <div className="trading-chart-heading">
          <div className="trading-chart-title-row">
            <strong>{chartQuery.data?.instrument.display_symbol ?? instrumentId}</strong>
            <span>· {interval.toUpperCase()} · {chartQuery.data?.instrument.venue ?? resolvedBinding?.provider ?? 'Omnix'}</span>
            <i className={`trading-stream-dot ${streamStatus}`} aria-label={`Feed ${streamStatus}`} />
          </div>
          {latest ? (
            <div className="trading-chart-ohlc">
              <span>O <b>{price(latest.open)}</b></span>
              <span>H <b>{price(latest.high)}</b></span>
              <span>L <b>{price(latest.low)}</b></span>
              <span>C <b>{price(latest.close)}</b></span>
              <span className={direction}>{change >= 0 ? '+' : ''}{price(String(change))} ({changePercent >= 0 ? '+' : ''}{changePercent.toFixed(2)}%)</span>
            </div>
          ) : null}
        </div>

        <div
          className="trading-chart-provenance"
          title={`${resolvedBinding?.provider ?? 'Resolving provider'} · ${resolvedBinding?.is_official_api ? 'official API' : 'unofficial API'} · ${provenance?.freshness_mode ?? 'loading'}`}
        >
          <span>{resolvedBinding?.provider ?? 'resolving'}</span>
          <span className={`stream-${streamStatus}`}>{streamStatus}</span>
        </div>

        {active ? (
          <div className="trading-drawing-manager" onPointerDown={(event) => event.stopPropagation()}>
            <button type="button" onClick={() => drawings.undo()} aria-label="Undo drawing">↶</button>
            <button type="button" onClick={() => drawings.redo()} aria-label="Redo drawing">↷</button>
            <button type="button" onClick={() => adapterRef.current && downloadDataUrl(adapterRef.current.snapshotDataUrl(), `${chartId}.png`)} aria-label="Snapshot chart">PNG</button>
            {drawings.hasConflict ? (
              <>
                <span role="status">Drawing conflict</span>
                <button type="button" onClick={() => void drawings.resolveConflict('reload')}>Reload server</button>
                <button type="button" onClick={() => void drawings.resolveConflict('overwrite')}>Overwrite server</button>
              </>
            ) : null}
            {selectedDrawing ? (
              <>
                <input aria-label="Drawing color" type="color" value={selectedDrawing.style?.color ?? '#66d9e8'} onChange={(event) => drawings.updateSelected({ style: { ...(selectedDrawing.style ?? { lineWidth: 2, lineStyle: 'solid' }), color: event.target.value } })} />
                <button type="button" aria-pressed={Boolean(selectedDrawing.locked)} onClick={() => drawings.updateSelected({ locked: !selectedDrawing.locked })}>{selectedDrawing.locked ? 'Unlock' : 'Lock'}</button>
                <button type="button" aria-pressed={Boolean(selectedDrawing.hidden)} onClick={() => drawings.updateSelected({ hidden: !selectedDrawing.hidden })}>{selectedDrawing.hidden ? 'Show' : 'Hide'}</button>
                {selectedDrawing.toolType === 'text' ? <input aria-label="Drawing text" type="text" value={selectedDrawing.text ?? ''} onChange={(event) => drawings.updateSelected({ text: event.target.value })} /> : null}
                <button type="button" onClick={() => drawings.removeSelected()} aria-label="Delete selected drawing">×</button>
              </>
            ) : null}
          </div>
        ) : null}
      </header>
      <div className="trading-chart-stage">
        <div ref={hostRef} className="trading-chart-canvas" aria-label={`${instrumentId} ${interval} chart`} />
        <TradingDrawingOverlay
          adapter={adapter}
          instrumentId={instrumentId}
          tool={active ? drawingTool : 'cursor'}
          snapMode={drawingSnapMode}
          drawings={drawings.state.drawings}
          selectedId={drawings.state.selectedId}
          onAdd={drawings.add}
          onSelect={drawings.select}
          onMovePoint={drawings.movePoint}
          onTranslateDrawing={drawings.translate}
          onAlertAtPoint={active ? setAlertPlacement : undefined}
        />
        <TradingChartAlertOverlay
          adapter={adapter}
          instrumentId={instrumentId}
          bindingId={provenance?.requested_binding ?? bindingId ?? resolvedBinding?.binding_id ?? null}
          interval={interval}
          latestPrice={latestClose}
          placement={alertPlacement}
          onPlacementConsumed={clearAlertPlacement}
        />
      </div>
      {chartQuery.isLoading ? <div className="trading-chart-state">Loading historical bars…</div> : null}
      {chartQuery.error ? <div className="trading-chart-state error">{chartQuery.error.message}</div> : null}
      {streamError ? <div className="trading-chart-state error">{streamError}</div> : null}
      {indicatorError ? <div className="trading-chart-state error">Indicator calculation failed: {indicatorError}</div> : null}
      <footer>
        <nav aria-label={`${chartId} visible range`} onPointerDown={(event) => event.stopPropagation()}>
          {ranges.map((range) => (
            <button key={range.label} type="button" onClick={() => showRange(range.days)}>{range.label}</button>
          ))}
        </nav>
        <div className="trading-chart-footer-meta">
          <span>{provenance?.as_of ? new Date(provenance.as_of).toLocaleTimeString() : 'Awaiting data'}</span>
          <span>{provenance?.cached ? 'cached' : 'live source'}</span>
          <span>{drawings.status}</span>
        </div>
      </footer>
    </article>
  );
}
