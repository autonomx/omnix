import { useQuery } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';
import { tradingApi } from './tradingApi';
import { TradingChartAdapter, type TradingChartType } from './chart/chartAdapter';
import type { TradingChartSynchronization } from './chart/chartSynchronization';
import { TradingDrawingOverlay } from './drawings/TradingDrawingOverlay';
import './drawings/TradingDrawingOverlay.css';
import { useTradingDrawings } from './drawings/useTradingDrawings';
import type { CoreIndicatorInstance } from './indicators/coreIndicators';
import { tradingStreamHub, type TradingStreamStatus } from './streaming/tradingStreamHub';
import { useTradingStore } from './tradingStore';
import type { MarketBar, TradingStreamMessage } from './tradingTypes';

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
  const drawingTool = useTradingStore((state) => state.drawingTool);
  const drawings = useTradingDrawings(instrumentId);
  const [adapter, setAdapter] = useState<TradingChartAdapter | null>(null);
  const [streamStatus, setStreamStatus] = useState<TradingStreamStatus>('connecting');
  const [streamError, setStreamError] = useState<string | null>(null);
  const chartQuery = useQuery({
    queryKey: ['trading', 'bars', instrumentId, bindingId, interval],
    queryFn: () => tradingApi.bars(instrumentId, interval, 1_000, bindingId),
    enabled: Boolean(instrumentId),
    staleTime: 15_000,
  });

  useEffect(() => {
    if (!hostRef.current) return;
    const next = new TradingChartAdapter(hostRef.current, chartType);
    adapterRef.current = next;
    setAdapter(next);
    const unregister = synchronization.register(chartId, next);
    return () => {
      unregister();
      next.destroy();
      adapterRef.current = null;
      setAdapter(null);
    };
  }, [chartId, synchronization]);

  useEffect(() => {
    const bars = chartQuery.data?.bars ?? [];
    barsRef.current = bars;
    adapterRef.current?.setBars(bars);
    adapterRef.current?.setIndicators(bars, indicators);
  }, [chartQuery.data]);

  useEffect(() => {
    adapterRef.current?.setChartType(chartType, barsRef.current);
  }, [chartType]);

  useEffect(() => {
    adapterRef.current?.setIndicators(barsRef.current, indicators);
  }, [indicators]);

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
          adapterRef.current.setIndicators(barsRef.current, indicators);
        }
      },
      (status) => {
        setStreamStatus(status);
        if (status === 'closed' || status === 'error') void chartQuery.refetch();
      },
      resolved.binding_id,
    );
  }, [chartId, instrumentId, interval, indicators, chartQuery.data?.binding.binding_id]);

  const provenance = chartQuery.data?.provenance;
  const resolvedBinding = chartQuery.data?.binding;
  return (
    <article
      className={`trading-chart-panel${active ? ' active' : ''}`}
      data-chart-id={chartId}
      data-stream-status={streamStatus}
      onPointerDown={onActivate}
      aria-label={`${chartId}${active ? ', active chart' : ''}`}
    >
      <header>
        <div>
          <strong>{chartQuery.data?.instrument.display_symbol ?? instrumentId}</strong>
          <span>{interval} · {chartType}</span>
          <span>{indicators.filter((item) => item.enabled).map((item) => item.id.toUpperCase()).join(' · ')}</span>
        </div>
        <div className="trading-chart-provenance">
          <span>{resolvedBinding?.provider ?? 'resolving'}</span>
          <span>{resolvedBinding?.is_official_api ? 'official' : 'unofficial'}</span>
          <span>{provenance?.freshness_mode ?? 'loading'}</span>
          <span className={`stream-${streamStatus}`}>{streamStatus}</span>
          <span>{drawings.status}</span>
        </div>
        {active ? (
          <div className="trading-drawing-actions">
            <button type="button" onClick={(event) => { event.stopPropagation(); drawings.undo(); }} aria-label="Undo drawing">↶</button>
            <button type="button" onClick={(event) => { event.stopPropagation(); drawings.redo(); }} aria-label="Redo drawing">↷</button>
            <button type="button" onClick={(event) => { event.stopPropagation(); drawings.removeSelected(); }} aria-label="Delete selected drawing">×</button>
          </div>
        ) : null}
      </header>
      <div className="trading-chart-stage">
        <div ref={hostRef} className="trading-chart-canvas" aria-label={`${instrumentId} ${interval} chart`} />
        <TradingDrawingOverlay
          adapter={adapter}
          instrumentId={instrumentId}
          tool={active ? drawingTool : 'cursor'}
          drawings={drawings.state.drawings}
          selectedId={drawings.state.selectedId}
          onAdd={drawings.add}
          onSelect={drawings.select}
          onMovePoint={drawings.movePoint}
        />
      </div>
      {chartQuery.isLoading ? <div className="trading-chart-state">Loading historical bars…</div> : null}
      {chartQuery.error ? <div className="trading-chart-state error">{chartQuery.error.message}</div> : null}
      {streamError ? <div className="trading-chart-state error">{streamError}</div> : null}
      <footer>
        <span>{provenance?.cached ? 'Cached dataset' : 'Provider dataset'}</span>
        <span>{provenance?.fallback_reason ?? resolvedBinding?.realtime_scope ?? ''}</span>
        <span>{provenance?.as_of ? `As of ${new Date(provenance.as_of).toLocaleString()}` : ''}</span>
        <span>{provenance?.dataset_fingerprint ? provenance.dataset_fingerprint.slice(0, 10) : ''}</span>
      </footer>
    </article>
  );
}
