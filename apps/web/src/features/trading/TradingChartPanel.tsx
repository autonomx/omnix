import { useQuery } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';
import { subscribeTradingStream, tradingApi } from './tradingApi';
import { TradingChartAdapter, type TradingChartType } from './chart/chartAdapter';
import type { MarketBar, TradingStreamMessage } from './tradingTypes';

function normalizeStreamBar(message: Extract<TradingStreamMessage, { type: 'bar' }>): MarketBar {
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
    provider: 'binance',
    provider_event_id: message.bar.provider_event_id,
    provider_sequence: message.bar.provider_sequence,
    ingestion_revision: message.bar.ingestion_revision,
    received_at: new Date().toISOString(),
  };
}

export function TradingChartPanel({
  instrumentId,
  interval,
  chartType,
}: {
  instrumentId: string;
  interval: string;
  chartType: TradingChartType;
}) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const adapterRef = useRef<TradingChartAdapter | null>(null);
  const barsRef = useRef<MarketBar[]>([]);
  const [streamStatus, setStreamStatus] = useState<'connecting' | 'live' | 'closed' | 'error'>('connecting');
  const [streamError, setStreamError] = useState<string | null>(null);
  const chartQuery = useQuery({
    queryKey: ['trading', 'bars', instrumentId, interval],
    queryFn: () => tradingApi.bars(instrumentId, interval, 1_000),
    enabled: Boolean(instrumentId),
    staleTime: 15_000,
  });

  useEffect(() => {
    if (!hostRef.current) return;
    const adapter = new TradingChartAdapter(hostRef.current, chartType);
    adapterRef.current = adapter;
    return () => {
      adapter.destroy();
      adapterRef.current = null;
    };
  }, []);

  useEffect(() => {
    const bars = chartQuery.data?.bars ?? [];
    barsRef.current = bars;
    adapterRef.current?.setBars(bars);
  }, [chartQuery.data]);

  useEffect(() => {
    adapterRef.current?.setChartType(chartType, barsRef.current);
  }, [chartType]);

  useEffect(() => {
    if (!instrumentId) return;
    setStreamError(null);
    const unsubscribe = subscribeTradingStream(
      instrumentId,
      interval,
      (message) => {
        if (message.type === 'error') {
          setStreamError(message.message);
          return;
        }
        const bar = normalizeStreamBar(message);
        if (adapterRef.current?.updateBar(bar)) {
          const index = barsRef.current.findIndex((item) => item.start_time === bar.start_time);
          if (index >= 0) barsRef.current[index] = bar;
          else barsRef.current = [...barsRef.current, bar];
        }
      },
      (status) => {
        setStreamStatus(status);
        if (status === 'closed' || status === 'error') void chartQuery.refetch();
      },
    );
    return unsubscribe;
  }, [instrumentId, interval]);

  const provenance = chartQuery.data?.provenance;
  return (
    <article className="trading-chart-panel" data-stream-status={streamStatus}>
      <header>
        <div>
          <strong>{chartQuery.data?.instrument.display_symbol ?? instrumentId}</strong>
          <span>{interval} · {chartType}</span>
        </div>
        <div className="trading-chart-provenance">
          <span>{chartQuery.data?.binding.provider ?? 'binance'}</span>
          <span>{provenance?.freshness_mode ?? 'loading'}</span>
          <span className={`stream-${streamStatus}`}>{streamStatus}</span>
        </div>
      </header>
      <div ref={hostRef} className="trading-chart-canvas" aria-label={`${instrumentId} ${interval} chart`} />
      {chartQuery.isLoading ? <div className="trading-chart-state">Loading historical bars…</div> : null}
      {chartQuery.error ? <div className="trading-chart-state error">{chartQuery.error.message}</div> : null}
      {streamError ? <div className="trading-chart-state error">{streamError}</div> : null}
      <footer>
        <span>{provenance?.cached ? 'Cached dataset' : 'Provider dataset'}</span>
        <span>{provenance?.as_of ? `As of ${new Date(provenance.as_of).toLocaleString()}` : ''}</span>
        <span>{provenance?.dataset_fingerprint ? provenance.dataset_fingerprint.slice(0, 10) : ''}</span>
      </footer>
    </article>
  );
}
