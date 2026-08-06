import {
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
  createChart,
  type CandlestickData,
  type HistogramData,
  type IChartApi,
  type ISeriesApi,
  type LineData,
  type Time,
  type UTCTimestamp,
} from 'lightweight-charts';
import type { DrawingPoint } from '../drawings/drawingCommands';
import { indicatorPoints, type CoreIndicatorInstance } from '../indicators/coreIndicators';
import type { MarketBar } from '../tradingTypes';

export type TradingChartType = 'candlestick' | 'line';
export type TradingCrosshairPoint = { time: Time; price: number };
export type TradingVisibleRange = { from: Time; to: Time };
export type DrawingCoordinate = { x: number; y: number };

function timestamp(value: string): UTCTimestamp {
  const milliseconds = Date.parse(value);
  if (!Number.isFinite(milliseconds)) throw new Error(`Invalid Trading timestamp: ${value}`);
  return Math.floor(milliseconds / 1_000) as UTCTimestamp;
}

export function candlestickData(bar: MarketBar): CandlestickData<UTCTimestamp> {
  return { time: timestamp(bar.start_time), open: Number(bar.open), high: Number(bar.high), low: Number(bar.low), close: Number(bar.close) };
}
export function lineData(bar: MarketBar): LineData<UTCTimestamp> { return { time: timestamp(bar.start_time), value: Number(bar.close) }; }
export function volumeData(bar: MarketBar): HistogramData<UTCTimestamp> {
  return { time: timestamp(bar.start_time), value: Number(bar.volume), color: Number(bar.close) >= Number(bar.open) ? 'rgba(32,201,151,.45)' : 'rgba(255,107,107,.42)' };
}

export class TradingChartAdapter {
  private readonly chart: IChartApi;
  private priceSeries: ISeriesApi<'Candlestick'> | ISeriesApi<'Line'>;
  private readonly volumeSeries: ISeriesApi<'Histogram'>;
  private readonly indicatorSeries = new Map<string, ISeriesApi<'Line'>>();
  private chartType: TradingChartType;
  private readonly revisions = new Map<number, number>();
  private destroyed = false;

  constructor(container: HTMLElement, chartType: TradingChartType = 'candlestick') {
    this.chartType = chartType;
    this.chart = createChart(container, {
      autoSize: true,
      layout: { background: { color: 'transparent' }, textColor: '#9eacbd' },
      grid: { vertLines: { color: 'rgba(120,145,170,.08)' }, horzLines: { color: 'rgba(120,145,170,.08)' } },
      rightPriceScale: { borderColor: 'rgba(140,160,180,.18)' },
      timeScale: { borderColor: 'rgba(140,160,180,.18)', timeVisible: true, secondsVisible: false },
    });
    this.priceSeries = this.createPriceSeries(chartType);
    this.volumeSeries = this.chart.addSeries(HistogramSeries, { priceScaleId: 'volume', priceFormat: { type: 'volume' } });
    this.volumeSeries.priceScale().applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });
  }

  private createPriceSeries(type: TradingChartType): ISeriesApi<'Candlestick'> | ISeriesApi<'Line'> {
    if (type === 'line') return this.chart.addSeries(LineSeries, { color: '#4dabf7', lineWidth: 2 });
    return this.chart.addSeries(CandlestickSeries, { upColor: '#20c997', downColor: '#ff6b6b', borderVisible: false, wickUpColor: '#20c997', wickDownColor: '#ff6b6b' });
  }

  setChartType(type: TradingChartType, bars: readonly MarketBar[]): void {
    this.assertActive();
    if (type === this.chartType) return;
    this.chart.removeSeries(this.priceSeries);
    this.chartType = type;
    this.priceSeries = this.createPriceSeries(type);
    this.setBars(bars, false);
  }

  setBars(bars: readonly MarketBar[], fit = true): void {
    this.assertActive();
    this.revisions.clear();
    for (const bar of bars) this.revisions.set(timestamp(bar.start_time), bar.ingestion_revision);
    if (this.chartType === 'candlestick') (this.priceSeries as ISeriesApi<'Candlestick'>).setData(bars.map(candlestickData));
    else (this.priceSeries as ISeriesApi<'Line'>).setData(bars.map(lineData));
    this.volumeSeries.setData(bars.map(volumeData));
    if (fit) this.chart.timeScale().fitContent();
  }

  setIndicators(bars: readonly MarketBar[], indicators: readonly CoreIndicatorInstance[]): void {
    this.assertActive();
    const enabled = new Set(indicators.filter((item) => item.enabled).map((item) => `${item.id}:${item.period}`));
    for (const [key, series] of this.indicatorSeries) {
      if (!enabled.has(key)) { this.chart.removeSeries(series); this.indicatorSeries.delete(key); }
    }
    for (const instance of indicators.filter((item) => item.enabled)) {
      const key = `${instance.id}:${instance.period}`;
      let series = this.indicatorSeries.get(key);
      if (!series) {
        const paneIndex = instance.id === 'rsi' ? 1 : 0;
        const color = instance.id === 'sma' ? '#ffd43b' : instance.id === 'ema' ? '#e599f7' : '#5c7cfa';
        series = this.chart.addSeries(LineSeries, { color, lineWidth: 2, title: `${instance.id.toUpperCase()} ${instance.period}`, priceScaleId: instance.id === 'rsi' ? 'rsi' : 'right' }, paneIndex);
        this.indicatorSeries.set(key, series);
      }
      series.setData(indicatorPoints(bars, instance).map((point) => ({ time: timestamp(point.time), value: point.value })));
    }
  }

  updateBar(bar: MarketBar): boolean {
    this.assertActive();
    const time = timestamp(bar.start_time);
    const previousRevision = this.revisions.get(time) ?? 0;
    if (bar.ingestion_revision < previousRevision) return false;
    this.revisions.set(time, bar.ingestion_revision);
    if (this.chartType === 'candlestick') (this.priceSeries as ISeriesApi<'Candlestick'>).update(candlestickData(bar));
    else (this.priceSeries as ISeriesApi<'Line'>).update(lineData(bar));
    this.volumeSeries.update(volumeData(bar));
    return true;
  }

  projectDrawingPoint(point: DrawingPoint): DrawingCoordinate | null {
    this.assertActive();
    const x = this.chart.timeScale().timeToCoordinate(timestamp(point.time));
    const y = this.priceSeries.priceToCoordinate(point.price);
    return x === null || y === null ? null : { x, y };
  }

  drawingPointFromCoordinate(x: number, y: number): DrawingPoint | null {
    this.assertActive();
    const time = this.chart.timeScale().coordinateToTime(x);
    const price = this.priceSeries.coordinateToPrice(y);
    if (typeof time !== 'number' || price === null) return null;
    return { time: new Date(time * 1_000).toISOString(), price };
  }

  onCrosshair(listener: (point: TradingCrosshairPoint | null) => void): () => void {
    this.assertActive();
    const handler = (parameter: { time?: Time; seriesData: Map<unknown, unknown> }) => {
      if (parameter.time === undefined) { listener(null); return; }
      const datum = parameter.seriesData.get(this.priceSeries) as { close?: number; value?: number } | undefined;
      const price = datum?.close ?? datum?.value;
      listener(typeof price === 'number' ? { time: parameter.time, price } : null);
    };
    this.chart.subscribeCrosshairMove(handler);
    return () => this.chart.unsubscribeCrosshairMove(handler);
  }
  setCrosshair(point: TradingCrosshairPoint | null): void { this.assertActive(); if (point === null) this.chart.clearCrosshairPosition(); else this.chart.setCrosshairPosition(point.price, point.time, this.priceSeries); }
  onVisibleRange(listener: (range: TradingVisibleRange | null) => void): () => void { this.assertActive(); const handler = (range: TradingVisibleRange | null) => listener(range); this.chart.timeScale().subscribeVisibleTimeRangeChange(handler); return () => this.chart.timeScale().unsubscribeVisibleTimeRangeChange(handler); }
  setVisibleRange(range: TradingVisibleRange): void { this.assertActive(); this.chart.timeScale().setVisibleRange(range); }
  fitContent(): void { this.assertActive(); this.chart.timeScale().fitContent(); }
  api(): IChartApi { this.assertActive(); return this.chart; }
  destroy(): void { if (this.destroyed) return; this.destroyed = true; this.revisions.clear(); this.indicatorSeries.clear(); this.chart.remove(); }
  private assertActive(): void { if (this.destroyed) throw new Error('Trading chart adapter is disposed'); }
}
