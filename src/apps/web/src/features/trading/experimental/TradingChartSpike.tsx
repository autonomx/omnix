import { useEffect, useMemo, useRef, useState } from 'react';
import {
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type Time,
  type UTCTimestamp,
} from 'lightweight-charts';
import {
  SpikeLifecycleRegistry,
  SynchronizationGuard,
  calculateRsi,
  generateSpikeBars,
  type DrawingPoint,
  type TrendDrawing,
} from './tradingSpikeCore';

const lifecycle = new SpikeLifecycleRegistry();
const syncGuard = new SynchronizationGuard();

type SyncMessage = { source: string; time: Time; price: number };
type SyncSubscriber = (message: SyncMessage) => void;
const syncSubscribers = new Set<SyncSubscriber>();

function publishCrosshair(message: SyncMessage) {
  syncSubscribers.forEach((subscriber) => subscriber(message));
}

function useDragPoint(
  drawing: TrendDrawing,
  setDrawing: (drawing: TrendDrawing) => void,
  endpoint: 'start' | 'end',
  width: number,
  height: number,
) {
  return (event: React.PointerEvent<SVGCircleElement>) => {
    event.currentTarget.setPointerCapture(event.pointerId);
    const target = event.currentTarget.ownerSVGElement;
    if (!target) return;
    const bounds = target.getBoundingClientRect();
    const onMove = (move: PointerEvent) => {
      const x = Math.max(0, Math.min(width, move.clientX - bounds.left));
      const y = Math.max(0, Math.min(height, move.clientY - bounds.top));
      const point: DrawingPoint = {
        time: Math.round(1_700_000_000 + x * 60),
        price: Math.round((45_000 - y * 15) * 100) / 100,
      };
      setDrawing(endpoint === 'start' ? { ...drawing, start: point } : { ...drawing, end: point });
    };
    const onUp = () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  };
}

function DrawingOverlay({ drawing, setDrawing }: { drawing: TrendDrawing; setDrawing: (drawing: TrendDrawing) => void }) {
  const width = 600;
  const height = 280;
  const toX = (point: DrawingPoint) => (point.time - 1_700_000_000) / 60;
  const toY = (point: DrawingPoint) => (45_000 - point.price) / 15;
  const startDrag = useDragPoint(drawing, setDrawing, 'start', width, height);
  const endDrag = useDragPoint(drawing, setDrawing, 'end', width, height);
  return (
    <svg aria-label="Experimental chart drawing overlay" viewBox={`0 0 ${width} ${height}`} className="trading-spike-drawing">
      <line x1={toX(drawing.start)} y1={toY(drawing.start)} x2={toX(drawing.end)} y2={toY(drawing.end)} />
      <line x1="0" y1="150" x2={width} y2="150" className="horizontal" />
      <circle cx={toX(drawing.start)} cy={toY(drawing.start)} r="7" onPointerDown={startDrag} />
      <circle cx={toX(drawing.end)} cy={toY(drawing.end)} r="7" onPointerDown={endDrag} />
    </svg>
  );
}

function SpikeChart({ id, intervalSeconds }: { id: string; intervalSeconds: number }) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const bars = useMemo(() => generateSpikeBars(5_000, 1_700_000_000, intervalSeconds), [intervalSeconds]);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const chart = createChart(host, {
      autoSize: true,
      layout: { background: { color: 'transparent' }, textColor: '#aab5c5' },
      grid: { vertLines: { color: 'rgba(120,140,165,.10)' }, horzLines: { color: 'rgba(120,140,165,.10)' } },
    });
    lifecycle.charts += 1;
    chartRef.current = chart;
    const candles = chart.addSeries(CandlestickSeries, { upColor: '#20c997', downColor: '#ff6b6b' });
    const volume = chart.addSeries(HistogramSeries, { priceScaleId: 'volume' });
    const rsi = chart.addSeries(LineSeries, { priceScaleId: 'rsi', color: '#5c7cfa' }, 1);
    candleRef.current = candles;
    candles.setData(
      bars.map((bar) => ({
        time: bar.time as UTCTimestamp,
        open: bar.open,
        high: bar.high,
        low: bar.low,
        close: bar.close,
      })),
    );
    volume.setData(bars.map((bar) => ({ time: bar.time as UTCTimestamp, value: bar.volume })));
    rsi.setData(calculateRsi(bars).map((point) => ({ time: point.time as UTCTimestamp, value: point.value })));
    chart.timeScale().fitContent();

    const crosshairHandler = (parameter: { time?: Time; seriesData: Map<unknown, unknown> }) => {
      if (parameter.time === undefined) return;
      const datum = parameter.seriesData.get(candles) as { close?: number } | undefined;
      if (typeof datum?.close !== 'number') return;
      syncGuard.run(`publish:${id}`, () => publishCrosshair({ source: id, time: parameter.time!, price: datum.close! }));
    };
    chart.subscribeCrosshairMove(crosshairHandler);
    lifecycle.listeners += 1;
    const subscriber: SyncSubscriber = (message) => {
      if (message.source === id) return;
      syncGuard.run(`apply:${id}`, () => chart.setCrosshairPosition(message.price, message.time, candles));
    };
    syncSubscribers.add(subscriber);
    lifecycle.subscriptions += 1;

    return () => {
      syncSubscribers.delete(subscriber);
      lifecycle.subscriptions -= 1;
      chart.unsubscribeCrosshairMove(crosshairHandler);
      lifecycle.listeners -= 1;
      candleRef.current = null;
      chartRef.current = null;
      chart.remove();
      lifecycle.charts -= 1;
    };
  }, [bars, id]);

  return <div ref={hostRef} data-testid={`trading-spike-chart-${id}`} className="trading-spike-chart" />;
}

export function TradingChartSpike() {
  const [drawing, setDrawing] = useState<TrendDrawing>({
    id: 'spike-trend-1',
    start: { time: 1_700_006_000, price: 41_500 },
    end: { time: 1_700_024_000, price: 43_100 },
  });
  return (
    <section className="trading-chart-spike" aria-label="Trading chart feasibility spike">
      <p>This component is experimental and must not be production-routed before ADR acceptance.</p>
      <div className="trading-spike-grid">
        <SpikeChart id="one-minute" intervalSeconds={60} />
        <SpikeChart id="five-minute" intervalSeconds={300} />
        <SpikeChart id="fifteen-minute" intervalSeconds={900} />
        <SpikeChart id="hourly" intervalSeconds={3_600} />
      </div>
      <DrawingOverlay drawing={drawing} setDrawing={setDrawing} />
    </section>
  );
}

export function assertTradingSpikeClean() {
  lifecycle.assertClean();
}
