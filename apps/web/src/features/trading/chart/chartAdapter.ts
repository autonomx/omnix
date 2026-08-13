import {
  AreaSeries,
  BarSeries,
  BaselineSeries,
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
import { indicatorOutputs, type CoreIndicatorInstance, type IndicatorOutput } from '../indicators/coreIndicators';
import type { MarketBar } from '../tradingTypes';

export type TradingChartType = 'candlestick' | 'bar' | 'line' | 'area' | 'baseline';
export type TradingCrosshairPoint = { time: Time; price: number };
export type TradingVisibleRange = { from: Time; to: Time };
export type DrawingCoordinate = { x: number; y: number };
type PriceSeries =
  | ISeriesApi<'Candlestick'>
  | ISeriesApi<'Bar'>
  | ISeriesApi<'Line'>
  | ISeriesApi<'Area'>
  | ISeriesApi<'Baseline'>;
type IndicatorSeries = ISeriesApi<'Line'> | ISeriesApi<'Histogram'>;

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

function indicatorColor(output: IndicatorOutput): string {
  if (output.key.includes('upper')) return '#74c0fc';
  if (output.key.includes('lower')) return '#74c0fc';
  if (output.key.includes('middle')) return '#a5d8ff';
  if (output.key.includes('signal')) return '#ff922b';
  if (output.key.includes('histogram')) return '#20c997';
  if (output.key.startsWith('atr')) return '#ffa94d';
  if (output.key.startsWith('vwap')) return '#ffd43b';
  if (output.key.startsWith('sma')) return '#ffd43b';
  if (output.key.startsWith('ema')) return '#e599f7';
  return '#5c7cfa';
}

export class TradingChartAdapter {
  private readonly chart: IChartApi;
  private priceSeries: PriceSeries;
  private readonly volumeSeries: ISeriesApi<'Histogram'>;
  private readonly indicatorSeries = new Map<string, IndicatorSeries>();
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

  private createPriceSeries(type: TradingChartType): PriceSeries {
    if (type === 'line') return this.chart.addSeries(LineSeries, { color: '#4dabf7', lineWidth: 2 });
    if (type === 'area') return this.chart.addSeries(AreaSeries, { lineColor: '#4dabf7', topColor: 'rgba(77,171,247,.35)', bottomColor: 'rgba(77,171,247,.02)', lineWidth: 2 });
    if (type === 'baseline') return this.chart.addSeries(BaselineSeries, { baseValue: { type: 'price', price: 0 }, topLineColor: '#20c997', bottomLineColor: '#ff6b6b', lineWidth: 2 });
    if (type === 'bar') return this.chart.addSeries(BarSeries, { upColor: '#20c997', downColor: '#ff6b6b', openVisible: true, thinBars: false });
    return this.chart.addSeries(CandlestickSeries, { upColor: '#20c997', downColor: '#ff6b6b', borderVisible: false, wickUpColor: '#20c997', wickDownColor: '#ff6b6b' });
  }

  private setPriceData(bars: readonly MarketBar[]): void {
    if (this.chartType === 'candlestick') (this.priceSeries as ISeriesApi<'Candlestick'>).setData(bars.map(candlestickData));
    else if (this.chartType === 'bar') (this.priceSeries as ISeriesApi<'Bar'>).setData(bars.map(candlestickData));
    else if (this.chartType === 'area') (this.priceSeries as ISeriesApi<'Area'>).setData(bars.map(lineData));
    else if (this.chartType === 'baseline') (this.priceSeries as ISeriesApi<'Baseline'>).setData(bars.map(lineData));
    else (this.priceSeries as ISeriesApi<'Line'>).setData(bars.map(lineData));
  }

  private updatePriceData(bar: MarketBar): void {
    if (this.chartType === 'candlestick') (this.priceSeries as ISeriesApi<'Candlestick'>).update(candlestickData(bar));
    else if (this.chartType === 'bar') (this.priceSeries as ISeriesApi<'Bar'>).update(candlestickData(bar));
    else if (this.chartType === 'area') (this.priceSeries as ISeriesApi<'Area'>).update(lineData(bar));
    else if (this.chartType === 'baseline') (this.priceSeries as ISeriesApi<'Baseline'>).update(lineData(bar));
    else (this.priceSeries as ISeriesApi<'Line'>).update(lineData(bar));
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
    this.setPriceData(bars);
    this.volumeSeries.setData(bars.map(volumeData));
    if (fit) this.chart.timeScale().fitContent();
  }

  setIndicators(bars: readonly MarketBar[], indicators: readonly CoreIndicatorInstance[]): void {
    const outputs = indicators.filter((item) => item.enabled).flatMap((item) => indicatorOutputs(bars, item));
    this.setIndicatorOutputs(outputs);
  }

  setIndicatorOutputs(outputs: readonly IndicatorOutput[]): void {
    this.assertActive();
    const enabled = new Set(outputs.map((output) => output.key));
    for (const [key, series] of this.indicatorSeries) {
      if (!enabled.has(key)) {
        this.chart.removeSeries(series);
        this.indicatorSeries.delete(key);
      }
    }
    for (const output of outputs) {
      let series = this.indicatorSeries.get(output.key);
      if (!series) {
        const color = indicatorColor(output);
        series = output.kind === 'histogram'
          ? this.chart.addSeries(HistogramSeries, { color, title: output.title, priceScaleId: `indicator:${output.key}` }, output.pane)
          : this.chart.addSeries(LineSeries, { color, lineWidth: 2, title: output.title, priceScaleId: output.pane === 1 ? `indicator:${output.key}` : 'right' }, output.pane);
        this.indicatorSeries.set(output.key, series);
      }
      const data = output.points.map((point) => ({ time: timestamp(point.time), value: point.value }));
      if (output.kind === 'histogram') (series as ISeriesApi<'Histogram'>).setData(data);
      else (series as ISeriesApi<'Line'>).setData(data);
    }
  }

  updateBar(bar: MarketBar): boolean {
    this.assertActive();
    const time = timestamp(bar.start_time);
    const previousRevision = this.revisions.get(time) ?? 0;
    if (bar.ingestion_revision < previousRevision) return false;
    this.revisions.set(time, bar.ingestion_revision);
    this.updatePriceData(bar);
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

  priceToCoordinate(price: number): number | null {
    this.assertActive();
    return this.priceSeries.priceToCoordinate(price);
  }

  priceFromCoordinate(y: number): number | null {
    this.assertActive();
    return this.priceSeries.coordinateToPrice(y);
  }

  snapshotDataUrl(): string {
    this.assertActive();
    return this.chart.takeScreenshot().toDataURL('image/png');
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
