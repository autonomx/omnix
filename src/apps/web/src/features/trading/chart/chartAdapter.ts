import {
  AreaSeries,
  BarSeries,
  BaselineSeries,
  CandlestickSeries,
  CrosshairMode,
  HistogramSeries,
  LineSeries,
  LineType,
  LineStyle,
  PriceScaleMode,
  createChart,
  type CandlestickData,
  type HistogramData,
  type IChartApi,
  type ISeriesApi,
  type LineData,
  type Logical,
  type MouseEventParams,
  type Time,
  type UTCTimestamp,
} from 'lightweight-charts';
import type { DrawingPoint } from '../drawings/drawingCommands';
import { indicatorOutputs, indicatorPaneScale, type CoreIndicatorId, type CoreIndicatorInstance, type IndicatorOutput } from '../indicators/coreIndicators';
import type { MarketBar } from '../tradingTypes';

export type TradingChartTypeGroup = 'candles' | 'lines' | 'areas' | 'columns' | 'profiles' | 'specialty';
export const TRADING_CHART_TYPE_GROUPS: readonly { id: TradingChartTypeGroup; label: string }[] = [
  { id: 'candles', label: 'Candles' },
  { id: 'lines', label: 'Lines' },
  { id: 'areas', label: 'Areas' },
  { id: 'columns', label: 'Columns' },
  { id: 'profiles', label: 'Volume and profile' },
  { id: 'specialty', label: 'Specialty charts' },
] as const;
export const TRADING_CHART_TYPE_OPTIONS = [
  { value: 'bar', label: 'Bars', group: 'candles', icon: 'bars' },
  { value: 'candlestick', label: 'Candles', group: 'candles', icon: 'candles' },
  { value: 'hollow-candles', label: 'Hollow candles', group: 'candles', icon: 'hollow-candles' },
  { value: 'volume-candles', label: 'Volume candles', group: 'candles', icon: 'volume-candles' },
  { value: 'line', label: 'Line', group: 'lines', icon: 'line' },
  { value: 'line-with-markers', label: 'Line with markers', group: 'lines', icon: 'line-with-markers' },
  { value: 'step-line', label: 'Step line', group: 'lines', icon: 'step-line' },
  { value: 'area', label: 'Area', group: 'areas', icon: 'area' },
  { value: 'hlc-area', label: 'HLC area', group: 'areas', icon: 'hlc-area' },
  { value: 'baseline', label: 'Baseline', group: 'areas', icon: 'baseline' },
  { value: 'columns', label: 'Columns', group: 'columns', icon: 'columns' },
  { value: 'high-low', label: 'High-low', group: 'columns', icon: 'high-low' },
  { value: 'volume-footprint', label: 'Volume footprint', group: 'profiles', icon: 'volume-footprint' },
  { value: 'time-price-opportunity', label: 'Time price opportunity', group: 'profiles', icon: 'time-price-opportunity' },
  { value: 'session-volume-profile', label: 'Session volume profile', group: 'profiles', icon: 'session-volume-profile' },
  { value: 'heikin-ashi', label: 'Heikin Ashi', group: 'specialty', icon: 'heikin-ashi' },
  { value: 'renko', label: 'Renko', group: 'specialty', icon: 'renko' },
  { value: 'line-break', label: 'Line break', group: 'specialty', icon: 'line-break' },
  { value: 'kagi', label: 'Kagi', group: 'specialty', icon: 'kagi' },
  { value: 'point-figure', label: 'Point & figure', group: 'specialty', icon: 'point-figure' },
  { value: 'range', label: 'Range', group: 'specialty', icon: 'range' },
] as const;
export type TradingChartType = typeof TRADING_CHART_TYPE_OPTIONS[number]['value'];
export type TradingChartAppearance = 'light' | 'dark';
export type TradingCrosshairPoint = { time: Time; price: number };
export type TradingVisibleRange = { from: Time; to: Time };
export type DrawingCoordinate = { x: number; y: number };
export type TradingIndicatorPaneGeometry = {
  id: string;
  paneIndex: number;
  top: number;
  height: number;
};
export type TradingIndicatorSelection = {
  id: CoreIndicatorId;
  x: number;
  y: number;
};
export type TradingPriceScaleSide = 'left' | 'right';
export const DEFAULT_TRADING_RIGHT_OFFSET = 10;
type PriceSeries =
  | ISeriesApi<'Candlestick'>
  | ISeriesApi<'Bar'>
  | ISeriesApi<'Line'>
  | ISeriesApi<'Area'>
  | ISeriesApi<'Baseline'>
  | ISeriesApi<'Histogram'>;
type IndicatorSeries = ISeriesApi<'Line'> | ISeriesApi<'Histogram'>;
type LogicalRange = { from: number; to: number };

export function constrainZoomOutRange(
  nextRange: LogicalRange,
  maxRange: LogicalRange | null,
  anchor: number,
): LogicalRange {
  if (!maxRange) return nextRange;
  const maxWidth = maxRange.to - maxRange.from;
  const nextWidth = nextRange.to - nextRange.from;
  if (maxWidth <= 0 || nextWidth <= maxWidth) return nextRange;
  const anchorRatio = (anchor - nextRange.from) / nextWidth;
  const from = anchor - maxWidth * anchorRatio;
  return { from, to: from + maxWidth };
}

function timestamp(value: string): UTCTimestamp {
  const milliseconds = Date.parse(value);
  if (!Number.isFinite(milliseconds)) throw new Error(`Invalid Trading timestamp: ${value}`);
  return Math.floor(milliseconds / 1_000) as UTCTimestamp;
}

function barCadenceMilliseconds(bars: readonly MarketBar[]): number | null {
  const intervals = bars
    .slice(1)
    .map((bar, index) => Date.parse(bar.start_time) - Date.parse(bars[index].start_time))
    .filter((value) => Number.isFinite(value) && value > 0)
    .sort((left, right) => left - right);
  if (intervals.length === 0) return null;
  return intervals[Math.floor(intervals.length / 2)] ?? null;
}

export function drawingTimeForLogicalIndex(logical: number, bars: readonly MarketBar[]): string | null {
  if (!Number.isFinite(logical) || bars.length === 0) return null;
  const nearestIndex = Math.round(logical);
  if (nearestIndex >= 0 && nearestIndex < bars.length) return bars[nearestIndex]?.start_time ?? null;
  const firstTime = Date.parse(bars[0].start_time);
  const cadence = barCadenceMilliseconds(bars);
  if (!Number.isFinite(firstTime) || cadence === null) return null;
  return new Date(firstTime + nearestIndex * cadence).toISOString();
}

export function drawingLogicalIndexForTime(value: string, bars: readonly MarketBar[]): number | null {
  if (bars.length === 0) return null;
  const milliseconds = Date.parse(value);
  if (!Number.isFinite(milliseconds)) return null;
  const exactIndex = bars.findIndex((bar) => Date.parse(bar.start_time) === milliseconds);
  if (exactIndex >= 0) return exactIndex;
  const firstTime = Date.parse(bars[0].start_time);
  const cadence = barCadenceMilliseconds(bars);
  if (!Number.isFinite(firstTime) || cadence === null) return null;
  return (milliseconds - firstTime) / cadence;
}

export function candlestickData(bar: MarketBar, multiplier = 1): CandlestickData<UTCTimestamp> {
  return { time: timestamp(bar.start_time), open: Number(bar.open) * multiplier, high: Number(bar.high) * multiplier, low: Number(bar.low) * multiplier, close: Number(bar.close) * multiplier };
}
export function lineData(bar: MarketBar, multiplier = 1): LineData<UTCTimestamp> { return { time: timestamp(bar.start_time), value: Number(bar.close) * multiplier }; }
function columnData(bar: MarketBar, multiplier = 1): HistogramData<UTCTimestamp> {
  return {
    time: timestamp(bar.start_time),
    value: Number(bar.close) * multiplier,
    color: Number(bar.close) >= Number(bar.open) ? 'rgba(32,201,151,.72)' : 'rgba(255,107,107,.72)',
  };
}
function volumeCandleData(bar: MarketBar, bars: readonly MarketBar[], multiplier = 1): CandlestickData<UTCTimestamp> {
  const volume = Number(bar.volume);
  const maximum = Math.max(...bars.map((item) => Number(item.volume)), volume, 1);
  const intensity = Math.min(1, Math.max(0, volume / maximum));
  const alpha = (0.35 + intensity * 0.6).toFixed(2);
  const color = Number(bar.close) >= Number(bar.open)
    ? `rgba(32,201,151,${alpha})`
    : `rgba(255,107,107,${alpha})`;
  return { ...candlestickData(bar, multiplier), color };
}
export function volumeData(bar: MarketBar): HistogramData<UTCTimestamp> {
  return { time: timestamp(bar.start_time), value: Number(bar.volume), color: Number(bar.close) >= Number(bar.open) ? 'rgba(32,201,151,.45)' : 'rgba(255,107,107,.42)' };
}

function isCandlestickType(type: TradingChartType): boolean {
  return type === 'candlestick'
    || type === 'hollow-candles'
    || type === 'volume-candles'
    || type === 'heikin-ashi'
    || type === 'renko'
    || type === 'line-break'
    || type === 'range';
}

function isBarType(type: TradingChartType): boolean {
  return type === 'bar' || type === 'high-low';
}

function isLineType(type: TradingChartType): boolean {
  return type === 'line' || type === 'line-with-markers' || type === 'step-line' || type === 'kagi' || type === 'point-figure';
}

function isAreaType(type: TradingChartType): boolean {
  return type === 'area' || type === 'hlc-area';
}

function isColumnType(type: TradingChartType): boolean {
  return type === 'columns'
    || type === 'volume-footprint'
    || type === 'time-price-opportunity'
    || type === 'session-volume-profile';
}

function isVolumeColumnType(type: TradingChartType): boolean {
  return type === 'volume-footprint' || type === 'session-volume-profile';
}

function syntheticBar(source: MarketBar, open: number, high: number, low: number, close: number, startTime: string): MarketBar {
  const duration = Math.max(1_000, Date.parse(source.end_time) - Date.parse(source.start_time));
  return {
    ...source,
    start_time: startTime,
    end_time: new Date(Date.parse(startTime) + duration).toISOString(),
    open: String(open),
    high: String(high),
    low: String(low),
    close: String(close),
  };
}

export function heikinAshiBars(bars: readonly MarketBar[]): MarketBar[] {
  let previousOpen: number | null = null;
  let previousClose: number | null = null;
  return bars.map((bar) => {
    const open = Number(bar.open);
    const high = Number(bar.high);
    const low = Number(bar.low);
    const close = Number(bar.close);
    const nextClose = (open + high + low + close) / 4;
    const nextOpen = previousOpen === null || previousClose === null
      ? (open + close) / 2
      : (previousOpen + previousClose) / 2;
    const nextHigh = Math.max(high, nextOpen, nextClose);
    const nextLow = Math.min(low, nextOpen, nextClose);
    previousOpen = nextOpen;
    previousClose = nextClose;
    return {
      ...bar,
      open: String(nextOpen),
      high: String(nextHigh),
      low: String(nextLow),
      close: String(nextClose),
    };
  });
}

function typicalRange(bars: readonly MarketBar[]): number {
  const ranges = bars.map((bar) => Math.abs(Number(bar.high) - Number(bar.low))).filter((range) => Number.isFinite(range) && range > 0).sort((left, right) => left - right);
  const median = ranges[Math.floor(ranges.length / 2)] ?? Math.abs(Number(bars[0]?.close ?? 1)) * 0.01;
  return Math.max(median, Math.abs(Number(bars[0]?.close ?? 1)) * 0.0001, Number.EPSILON);
}

export function renkoBars(bars: readonly MarketBar[]): MarketBar[] {
  if (bars.length === 0) return [];
  const brickSize = typicalRange(bars);
  let anchor = Number(bars[0].close);
  let lastTimestamp = Number.NEGATIVE_INFINITY;
  const output: MarketBar[] = [];
  for (const source of bars) {
    const close = Number(source.close);
    while (close - anchor >= brickSize || anchor - close >= brickSize) {
      const direction = close > anchor ? 1 : -1;
      const next = anchor + direction * brickSize;
      const start = Math.max(Date.parse(source.start_time), Number.isFinite(lastTimestamp) ? lastTimestamp + 1_000 : Date.parse(source.start_time));
      const open = anchor;
      output.push(syntheticBar(source, open, Math.max(open, next), Math.min(open, next), next, new Date(start).toISOString()));
      anchor = next;
      lastTimestamp = start;
    }
  }
  return output.length > 0 ? output : [syntheticBar(bars[0], anchor, anchor, anchor, anchor, bars[0].start_time)];
}

export function rangeBars(bars: readonly MarketBar[]): MarketBar[] {
  if (bars.length === 0) return [];
  const rangeSize = typicalRange(bars);
  let anchor = Number(bars[0].close);
  let lastTimestamp = Number.NEGATIVE_INFINITY;
  const output: MarketBar[] = [];
  for (const source of bars) {
    const high = Number(source.high);
    const low = Number(source.low);
    const extremes = high - anchor >= rangeSize ? 1 : anchor - low >= rangeSize ? -1 : 0;
    if (extremes === 0) continue;
    const next = anchor + extremes * rangeSize;
    const start = Math.max(Date.parse(source.start_time), Number.isFinite(lastTimestamp) ? lastTimestamp + 1_000 : Date.parse(source.start_time));
    output.push(syntheticBar(source, anchor, Math.max(anchor, next), Math.min(anchor, next), next, new Date(start).toISOString()));
    anchor = next;
    lastTimestamp = start;
  }
  return output.length > 0 ? output : [syntheticBar(bars[0], anchor, anchor, anchor, anchor, bars[0].start_time)];
}

export function lineBreakBars(bars: readonly MarketBar[]): MarketBar[] {
  if (bars.length === 0) return [];
  const output: MarketBar[] = [];
  const closes: number[] = [];
  for (const source of bars) {
    const close = Number(source.close);
    const previous = closes.slice(-3);
    const accepted = previous.length < 3 || close > Math.max(...previous) || close < Math.min(...previous);
    if (!accepted) continue;
    const open = closes.at(-1) ?? close;
    output.push(syntheticBar(source, open, Math.max(open, close), Math.min(open, close), close, source.start_time));
    closes.push(close);
  }
  return output.length > 0 ? output : [syntheticBar(bars[0], Number(bars[0].close), Number(bars[0].close), Number(bars[0].close), Number(bars[0].close), bars[0].start_time)];
}

export function reversalBars(bars: readonly MarketBar[]): MarketBar[] {
  if (bars.length === 0) return [];
  const reversal = typicalRange(bars);
  let anchor = Number(bars[0].close);
  let direction = 0;
  const output: MarketBar[] = [];
  for (const source of bars) {
    const close = Number(source.close);
    const delta = close - anchor;
    if (Math.abs(delta) < reversal) continue;
    const nextDirection = delta > 0 ? 1 : -1;
    if (direction !== 0 && nextDirection !== direction && Math.abs(delta) < reversal * 2) continue;
    output.push(syntheticBar(source, anchor, Math.max(anchor, close), Math.min(anchor, close), close, source.start_time));
    anchor = close;
    direction = nextDirection;
  }
  return output.length > 0 ? output : [syntheticBar(bars[0], anchor, anchor, anchor, anchor, bars[0].start_time)];
}

function displayBars(bars: readonly MarketBar[], type: TradingChartType): readonly MarketBar[] {
  if (type === 'heikin-ashi') return heikinAshiBars(bars);
  if (type === 'renko') return renkoBars(bars);
  if (type === 'range') return rangeBars(bars);
  if (type === 'line-break') return lineBreakBars(bars);
  if (type === 'kagi' || type === 'point-figure') return reversalBars(bars);
  return bars;
}

function indicatorColor(output: IndicatorOutput): string {
  if (output.key.startsWith('bull-market-band:sma')) return '#ff6b6b';
  if (output.key.startsWith('bull-market-band:ema')) return '#40ad50';
  if (output.key.includes('support') || output.key.includes('value-area-low')) return '#20c997';
  if (output.key.includes('resistance') || output.key.includes('value-area-high')) return '#ff6b6b';
  if (output.key.includes('poc')) return '#ffd43b';
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

function indicatorPaneId(output: IndicatorOutput): string | null {
  if (output.pane === 0) return null;
  return output.key.split(':', 1)[0] ?? null;
}

function indicatorLineStyle(value: IndicatorOutput['lineStyle']): LineStyle | undefined {
  if (value === 'dotted') return LineStyle.Dotted;
  if (value === 'dashed') return LineStyle.Dashed;
  if (value === 'large-dashed') return LineStyle.LargeDashed;
  if (value === 'sparse-dotted') return LineStyle.SparseDotted;
  if (value === 'solid') return LineStyle.Solid;
  return undefined;
}

function indicatorPriceFormat(precision: number | null | undefined): { priceFormat?: { type: 'price'; precision: number; minMove: number } } {
  if (precision === null || precision === undefined) return {};
  return { priceFormat: { type: 'price', precision, minMove: 10 ** -precision } };
}

export class TradingChartAdapter {
  private readonly chart: IChartApi;
  private priceSeries: PriceSeries;
  private readonly volumeSeries: ISeriesApi<'Histogram'>;
  private readonly indicatorSeries = new Map<string, IndicatorSeries>();
  private readonly indicatorSeriesPanes = new Map<string, number>();
  private readonly indicatorScaleRanges = new Map<string, { from: number; to: number }>();
  private indicatorPaneIds: string[] = [];
  private readonly indicatorPaneHeights = new Map<string, number>();
  private readonly restoredPaneHeights = new Map<string, number>();
  private fullscreenIndicatorId: string | null = null;
  private fullscreenMainPane = false;
  private readonly fullscreenPaneStretchFactors = new Map<number, number>();
  private maxZoomOutRange: LogicalRange | null = null;
  private rightOffset = DEFAULT_TRADING_RIGHT_OFFSET;
  private priceScaleSide: TradingPriceScaleSide = 'right';
  private priceScaleLabelsVisible = true;
  private priceScaleLinesVisible = true;
  private gridLinesVisible = true;
  private latestValueLabelVisible = true;
  private chartType: TradingChartType;
  private readonly revisions = new Map<number, number>();
  private readonly viewportListeners = new Set<() => void>();
  private bars: MarketBar[] = [];
  private indicatorOutputs: IndicatorOutput[] = [];
  private priceScaleMultiplier = 1;
  private destroyed = false;

  constructor(container: HTMLElement, chartType: TradingChartType = 'candlestick') {
    this.chartType = chartType;
    this.chart = createChart(container, {
      autoSize: true,
      layout: { background: { color: 'transparent' }, textColor: '#9eacbd' },
      crosshair: { mode: CrosshairMode.Normal },
      grid: { vertLines: { color: 'rgba(120,145,170,.08)' }, horzLines: { color: 'rgba(120,145,170,.08)' } },
      rightPriceScale: { borderColor: 'rgba(140,160,180,.18)' },
      timeScale: {
        borderColor: 'rgba(140,160,180,.18)',
        timeVisible: true,
        secondsVisible: false,
        fixLeftEdge: false,
        fixRightEdge: false,
        rightOffset: DEFAULT_TRADING_RIGHT_OFFSET,
      },
      handleScale: {
        mouseWheel: true,
        pinch: true,
        axisPressedMouseMove: { time: false, price: false },
        axisDoubleClickReset: { time: true, price: true },
      },
      handleScroll: {
        mouseWheel: true,
        pressedMouseMove: false,
        horzTouchDrag: true,
        vertTouchDrag: true,
      },
      kineticScroll: { mouse: true, touch: true },
    });
    this.priceSeries = this.createPriceSeries(chartType);
    this.volumeSeries = this.chart.addSeries(HistogramSeries, { priceScaleId: 'volume', priceFormat: { type: 'volume' } });
    this.volumeSeries.priceScale().applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });
  }

  private createPriceSeries(type: TradingChartType): PriceSeries {
    if (isLineType(type)) {
      return this.chart.addSeries(LineSeries, {
        color: '#4dabf7',
        lineWidth: 1,
        lineType: type === 'step-line' ? LineType.WithSteps : LineType.Simple,
        pointMarkersVisible: type === 'line-with-markers',
      });
    }
    if (isAreaType(type)) return this.chart.addSeries(AreaSeries, { lineColor: '#4dabf7', topColor: 'rgba(77,171,247,.35)', bottomColor: 'rgba(77,171,247,.02)', lineWidth: 1 });
    if (type === 'baseline') return this.chart.addSeries(BaselineSeries, { baseValue: { type: 'price', price: 0 }, topLineColor: '#20c997', bottomLineColor: '#ff6b6b', lineWidth: 1 });
    if (isColumnType(type)) return this.chart.addSeries(HistogramSeries, {
      priceScaleId: isVolumeColumnType(type) ? 'volume' : 'right',
      priceFormat: isVolumeColumnType(type) ? { type: 'volume' } : { type: 'price', precision: 2, minMove: 0.01 },
      base: 0,
    });
    if (isBarType(type)) return this.chart.addSeries(BarSeries, {
      upColor: '#20c997',
      downColor: '#ff6b6b',
      openVisible: type !== 'high-low',
      thinBars: type === 'high-low',
    });
    if (type === 'hollow-candles') {
      return this.chart.addSeries(CandlestickSeries, {
        upColor: 'transparent',
        downColor: '#ff6b6b',
        borderVisible: true,
        borderUpColor: '#20c997',
        borderDownColor: '#ff6b6b',
        wickUpColor: '#20c997',
        wickDownColor: '#ff6b6b',
      });
    }
    return this.chart.addSeries(CandlestickSeries, { upColor: '#20c997', downColor: '#ff6b6b', borderVisible: false, wickUpColor: '#20c997', wickDownColor: '#ff6b6b' });
  }

  private setPriceData(bars: readonly MarketBar[]): void {
    const visibleBars = displayBars(bars, this.chartType);
    if (isCandlestickType(this.chartType)) (this.priceSeries as ISeriesApi<'Candlestick'>).setData(visibleBars.map((bar) => this.chartType === 'volume-candles' ? volumeCandleData(bar, visibleBars, this.priceScaleMultiplier) : candlestickData(bar, this.priceScaleMultiplier)));
    else if (isBarType(this.chartType)) (this.priceSeries as ISeriesApi<'Bar'>).setData(visibleBars.map((bar) => candlestickData(bar, this.priceScaleMultiplier)));
    else if (isColumnType(this.chartType)) (this.priceSeries as ISeriesApi<'Histogram'>).setData(visibleBars.map((bar) => isVolumeColumnType(this.chartType) ? volumeData(bar) : columnData(bar, this.priceScaleMultiplier)));
    else if (isAreaType(this.chartType)) (this.priceSeries as ISeriesApi<'Area'>).setData(visibleBars.map((bar) => lineData(bar, this.priceScaleMultiplier)));
    else if (this.chartType === 'baseline') (this.priceSeries as ISeriesApi<'Baseline'>).setData(visibleBars.map((bar) => lineData(bar, this.priceScaleMultiplier)));
    else (this.priceSeries as ISeriesApi<'Line'>).setData(visibleBars.map((bar) => lineData(bar, this.priceScaleMultiplier)));
  }

  private updatePriceData(bar: MarketBar): void {
    if (this.chartType === 'heikin-ashi' || this.chartType === 'renko' || this.chartType === 'range' || this.chartType === 'line-break' || this.chartType === 'kagi' || this.chartType === 'point-figure') {
      this.setPriceData(this.bars);
      return;
    }
    if (isCandlestickType(this.chartType)) (this.priceSeries as ISeriesApi<'Candlestick'>).update(this.chartType === 'volume-candles' ? volumeCandleData(bar, this.bars, this.priceScaleMultiplier) : candlestickData(bar, this.priceScaleMultiplier));
    else if (isBarType(this.chartType)) (this.priceSeries as ISeriesApi<'Bar'>).update(candlestickData(bar, this.priceScaleMultiplier));
    else if (isColumnType(this.chartType)) (this.priceSeries as ISeriesApi<'Histogram'>).update(isVolumeColumnType(this.chartType) ? volumeData(bar) : columnData(bar, this.priceScaleMultiplier));
    else if (isAreaType(this.chartType)) (this.priceSeries as ISeriesApi<'Area'>).update(lineData(bar, this.priceScaleMultiplier));
    else if (this.chartType === 'baseline') (this.priceSeries as ISeriesApi<'Baseline'>).update(lineData(bar, this.priceScaleMultiplier));
    else (this.priceSeries as ISeriesApi<'Line'>).update(lineData(bar, this.priceScaleMultiplier));
  }

  setChartType(type: TradingChartType, bars: readonly MarketBar[]): void {
    this.assertActive();
    if (type === this.chartType) return;
    this.chart.removeSeries(this.priceSeries);
    this.chartType = type;
    this.priceSeries = this.createPriceSeries(type);
    this.priceSeries.applyOptions({ lastValueVisible: this.latestValueLabelVisible });
    this.setBars(bars, false);
  }

  setAppearance(appearance: TradingChartAppearance): void {
    this.assertActive();
    const light = appearance === 'light';
    const textColor = light ? '#536273' : '#9eacbd';
    const gridColor = light ? 'rgba(91,111,132,.14)' : 'rgba(120,145,170,.08)';
    const borderColor = light ? 'rgba(91,111,132,.28)' : 'rgba(140,160,180,.18)';
    this.chart.applyOptions({
      layout: { background: { color: 'transparent' }, textColor },
      grid: { vertLines: { color: gridColor }, horzLines: { color: gridColor } },
      leftPriceScale: { borderColor },
      rightPriceScale: { borderColor },
      timeScale: { borderColor },
    });
  }

  setBars(bars: readonly MarketBar[], fit = true): void {
    this.assertActive();
    const visibleRange = fit ? null : this.chart.timeScale().getVisibleLogicalRange();
    this.bars = [...bars];
    this.revisions.clear();
    for (const bar of bars) this.revisions.set(timestamp(bar.start_time), bar.ingestion_revision);
    this.setPriceData(bars);
    this.volumeSeries.setData(bars.map(volumeData));
    if (fit) this.fitContent();
    else if (visibleRange) this.chart.timeScale().setVisibleLogicalRange(visibleRange);
  }

  setIndicators(bars: readonly MarketBar[], indicators: readonly CoreIndicatorInstance[]): void {
    const outputs = indicators.filter((item) => item.enabled && item.visible !== false).flatMap((item) => indicatorOutputs(bars, item));
    this.setIndicatorOutputs(outputs);
  }

  setIndicatorOutputs(outputs: readonly IndicatorOutput[]): void {
    this.assertActive();
    this.indicatorOutputs = [...outputs];
    const paneIds = outputs.reduce<string[]>((ids, output) => {
      const paneId = indicatorPaneId(output);
      if (paneId && !ids.includes(paneId)) ids.push(paneId);
      return ids;
    }, []);

    const enabled = new Set(outputs.map((output) => output.key));
    for (const [key, series] of this.indicatorSeries) {
      if (!enabled.has(key)) {
        this.chart.removeSeries(series);
        this.indicatorSeries.delete(key);
        this.indicatorSeriesPanes.delete(key);
      }
    }
    for (const output of outputs) {
      if (output.visible === false) continue;
      const paneId = indicatorPaneId(output);
      const paneIndex = paneId === null ? 0 : paneIds.indexOf(paneId) + 1;
      // A custom price-scale ID creates an overlay scale in Lightweight Charts.
      // Pane indicators must use the pane's native right scale for its labels
      // and tick marks to render inside that pane.
      const priceScaleId = paneId === null ? this.priceScaleSide : 'right';
      let series = this.indicatorSeries.get(output.key);
      if (!series) {
        const color = output.color ?? indicatorColor(output);
        const lineStyle = indicatorLineStyle(output.lineStyle);
        const commonOptions = {
          color,
          title: output.valuesInStatusLine === false ? '' : output.title,
          lastValueVisible: output.labelsOnPriceScale === true,
          ...indicatorPriceFormat(output.precision),
        };
        series = output.kind === 'histogram'
          ? this.chart.addSeries(HistogramSeries, { ...commonOptions, priceScaleId }, paneIndex)
          : this.chart.addSeries(LineSeries, { ...commonOptions, ...(lineStyle === undefined ? {} : { lineStyle }), lineWidth: output.lineWidth ?? 1, priceScaleId }, paneIndex);
        this.indicatorSeries.set(output.key, series);
        this.indicatorSeriesPanes.set(output.key, paneIndex);
      } else if (this.indicatorSeriesPanes.get(output.key) !== paneIndex) {
        series.moveToPane(paneIndex);
        this.indicatorSeriesPanes.set(output.key, paneIndex);
      }
      if (output.kind === 'histogram') {
        (series as ISeriesApi<'Histogram'>).applyOptions({
          color: output.color ?? indicatorColor(output),
          title: output.valuesInStatusLine === false ? '' : output.title,
          lastValueVisible: output.labelsOnPriceScale === true,
          priceScaleId,
          ...indicatorPriceFormat(output.precision),
        });
      } else {
        const lineStyle = indicatorLineStyle(output.lineStyle);
        (series as ISeriesApi<'Line'>).applyOptions({
          color: output.color ?? indicatorColor(output),
          title: output.valuesInStatusLine === false ? '' : output.title,
          lastValueVisible: output.labelsOnPriceScale === true,
          lineWidth: output.lineWidth ?? 1,
          priceScaleId,
          ...(lineStyle === undefined ? {} : { lineStyle }),
          ...indicatorPriceFormat(output.precision),
        });
      }
      const data = output.points.map((point) => ({
        time: timestamp(point.time),
        value: output.pane === 0 ? point.value * this.priceScaleMultiplier : point.value,
      }));
      if (output.kind === 'histogram') (series as ISeriesApi<'Histogram'>).setData(data);
      else (series as ISeriesApi<'Line'>).setData(data);
    }
    this.indicatorPaneIds = paneIds;
    for (const [index, paneId] of paneIds.entries()) {
      const pane = this.chart.panes()[index + 1];
      if (!pane) continue;
      const scale = pane.priceScale('right');
      scale.applyOptions({
        visible: true,
        borderVisible: true,
        ticksVisible: true,
        minimumWidth: 58,
      });
      const range = indicatorPaneScale(paneId as CoreIndicatorInstance['id']);
      const visibleRange = this.indicatorScaleRanges.get(paneId);
      if (visibleRange) scale.setVisibleRange(visibleRange);
      else if (range) scale.setVisibleRange({ from: range.min, to: range.max });
    }
    for (const id of this.restoredPaneHeights.keys()) {
      if (!paneIds.includes(id)) this.restoredPaneHeights.delete(id);
    }
    for (const id of this.indicatorScaleRanges.keys()) {
      if (!paneIds.includes(id)) this.indicatorScaleRanges.delete(id);
    }
    for (const id of this.indicatorPaneHeights.keys()) {
      if (!paneIds.includes(id)) this.indicatorPaneHeights.delete(id);
    }
    for (let index = this.chart.panes().length - 1; index > paneIds.length; index -= 1) {
      const pane = this.chart.panes()[index];
      if (pane?.getSeries().length === 0) this.chart.removePane(index);
    }
  }

  indicatorPaneGeometry(): TradingIndicatorPaneGeometry[] {
    this.assertActive();
    const chartElement = this.chart.chartElement();
    const chartRect = chartElement.getBoundingClientRect();
    return this.indicatorPaneIds.flatMap((id, index) => {
      const paneIndex = index + 1;
      const pane = this.chart.panes()[paneIndex];
      const element = pane?.getHTMLElement();
      if (!element) return [];
      const rect = element.getBoundingClientRect();
      return [{ id, paneIndex, top: rect.top - chartRect.top, height: rect.height }];
    });
  }

  setIndicatorPaneMinimized(id: string, minimized: boolean): void {
    this.assertActive();
    if (this.fullscreenIndicatorId !== null) return;
    const index = this.indicatorPaneIds.indexOf(id);
    if (index < 0) return;
    const pane = this.chart.panes()[index + 1];
    if (!pane) return;
    if (minimized) {
      if (!this.restoredPaneHeights.has(id)) this.restoredPaneHeights.set(id, Math.max(100, pane.getHeight()));
      pane.setHeight(34);
      return;
    }
    pane.setHeight(this.restoredPaneHeights.get(id) ?? this.indicatorPaneHeights.get(id) ?? 140);
    this.restoredPaneHeights.delete(id);
  }

  resetIndicatorPaneView(id: string): void {
    this.assertActive();
    const index = this.indicatorPaneIds.indexOf(id);
    if (index < 0) return;
    const pane = this.chart.panes()[index + 1];
    const scale = pane?.priceScale('right');
    if (!scale) return;

    // Remove the manual range so future indicator updates keep the restored
    // default instead of immediately applying the user's previous drag.
    this.indicatorScaleRanges.delete(id);
    const range = indicatorPaneScale(id as CoreIndicatorInstance['id']);
    if (range) {
      scale.setAutoScale(false);
      scale.setVisibleRange({ from: range.min, to: range.max });
    } else {
      scale.setAutoScale(true);
    }
    this.notifyViewportChange();
  }

  resizeIndicatorPaneByPixels(id: string, edge: 'top' | 'bottom', deltaY: number): void {
    this.assertActive();
    if (this.fullscreenIndicatorId !== null || !Number.isFinite(deltaY) || deltaY === 0) return;
    const index = this.indicatorPaneIds.indexOf(id);
    if (index < 0) return;
    const pane = this.chart.panes()[index + 1];
    if (!pane || pane.getHeight() <= 34) return;
    const heightDelta = edge === 'top' ? -deltaY : deltaY;
    const nextHeight = Math.max(80, pane.getHeight() + heightDelta);
    if (Math.abs(nextHeight - pane.getHeight()) < 0.5) return;
    pane.setHeight(nextHeight);
    this.indicatorPaneHeights.set(id, nextHeight);
    this.notifyViewportChange();
  }

  setIndicatorPaneFullscreen(id: string | null): void {
    this.assertActive();
    if (id === null) {
      this.restoreFullscreenPaneHeights();
      return;
    }
    const indicatorIndex = this.indicatorPaneIds.indexOf(id);
    if (indicatorIndex < 0) return;
    const paneIndex = indicatorIndex + 1;
    const panes = this.chart.panes();
    if (!panes[paneIndex]) return;
    if (this.fullscreenIndicatorId !== id || this.fullscreenMainPane) {
      this.restoreFullscreenPaneHeights();
      this.fullscreenIndicatorId = id;
      this.fullscreenMainPane = false;
      this.captureFullscreenPaneState(panes);
    }
    this.applyFullscreenPaneHeights();
  }

  setMainPaneFullscreen(enabled: boolean): void {
    this.assertActive();
    if (!enabled) {
      this.restoreFullscreenPaneHeights();
      return;
    }
    if (!this.fullscreenMainPane || this.fullscreenIndicatorId !== null) {
      this.restoreFullscreenPaneHeights();
      this.fullscreenIndicatorId = null;
      this.fullscreenMainPane = true;
      this.captureFullscreenPaneState(this.chart.panes());
    }
    this.applyFullscreenPaneHeights();
  }

  refreshIndicatorPaneFullscreen(): void {
    this.assertActive();
    if (this.fullscreenIndicatorId !== null || this.fullscreenMainPane) this.applyFullscreenPaneHeights();
  }

  private captureFullscreenPaneState(panes: ReturnType<IChartApi['panes']>): void {
    this.fullscreenPaneStretchFactors.clear();
    for (const [index, pane] of panes.entries()) {
      this.fullscreenPaneStretchFactors.set(index, pane.getStretchFactor());
    }
  }

  private applyFullscreenPaneHeights(): void {
    if (this.fullscreenIndicatorId === null && !this.fullscreenMainPane) return;
    const indicatorIndex = this.fullscreenIndicatorId === null ? -1 : this.indicatorPaneIds.indexOf(this.fullscreenIndicatorId);
    if (!this.fullscreenMainPane && indicatorIndex < 0) {
      this.restoreFullscreenPaneHeights();
      return;
    }
    const panes = this.chart.panes();
    const focusedPaneIndex = this.fullscreenMainPane ? 0 : indicatorIndex + 1;
    if (!panes[focusedPaneIndex]) {
      this.restoreFullscreenPaneHeights();
      return;
    }
    for (const [index, pane] of panes.entries()) {
      const focused = index === focusedPaneIndex;
      pane.setStretchFactor(focused ? 1 : 0);
      const element = pane.getHTMLElement();
      if (element) {
        element.style.visibility = focused ? 'visible' : 'hidden';
        element.style.pointerEvents = focused ? 'auto' : 'none';
      }
    }
  }

  private restoreFullscreenPaneHeights(): void {
    if (this.fullscreenIndicatorId === null && !this.fullscreenMainPane) return;
    const panes = this.chart.panes();
    for (const [index, stretchFactor] of this.fullscreenPaneStretchFactors) panes[index]?.setStretchFactor(stretchFactor);
    for (const pane of panes) {
      const element = pane.getHTMLElement();
      if (element) {
        element.style.removeProperty('visibility');
        element.style.removeProperty('pointer-events');
      }
    }
    this.fullscreenIndicatorId = null;
    this.fullscreenMainPane = false;
    this.fullscreenPaneStretchFactors.clear();
  }

  updateBar(bar: MarketBar): boolean {
    this.assertActive();
    const time = timestamp(bar.start_time);
    const previousRevision = this.revisions.get(time) ?? 0;
    if (bar.ingestion_revision < previousRevision) return false;
    this.revisions.set(time, bar.ingestion_revision);
    const existingIndex = this.bars.findIndex((item) => timestamp(item.start_time) === time);
    if (existingIndex >= 0) this.bars[existingIndex] = bar;
    else this.bars.push(bar);
    this.updatePriceData(bar);
    this.volumeSeries.update(volumeData(bar));
    return true;
  }

  projectDrawingPoint(point: DrawingPoint): DrawingCoordinate | null {
    this.assertActive();
    const timeScale = this.chart.timeScale();
    const time = timestamp(point.time);
    const x = timeScale.timeToCoordinate(time)
      ?? (() => {
        const logical = drawingLogicalIndexForTime(point.time, this.bars);
        return logical === null ? null : timeScale.logicalToCoordinate(logical as Logical);
      })();
    const y = this.priceSeries.priceToCoordinate(point.price * this.priceScaleMultiplier);
    return x === null || y === null ? null : { x, y };
  }

  indicatorPointToCoordinate(key: string, point: { time: string; value: number }): DrawingCoordinate | null {
    this.assertActive();
    const series = this.indicatorSeries.get(key);
    if (!series) return null;
    const x = this.chart.timeScale().timeToCoordinate(timestamp(point.time));
    const y = this.indicatorValueToCoordinate(key, point.value);
    return x === null || y === null ? null : { x, y };
  }

  indicatorValueToCoordinate(key: string, value: number): number | null {
    this.assertActive();
    const series = this.indicatorSeries.get(key);
    if (!series) return null;
    const paneIndex = this.indicatorSeriesPanes.get(key) ?? 0;
    const pane = this.chart.panes()[paneIndex];
    const paneElement = pane?.getHTMLElement();
    const chartElement = this.chart.chartElement();
    if (!paneElement || !chartElement) return null;
    const localY = series.priceToCoordinate(paneIndex === 0 ? value * this.priceScaleMultiplier : value);
    if (localY === null) return null;
    const paneRect = paneElement.getBoundingClientRect();
    const chartRect = chartElement.getBoundingClientRect();
    return localY + paneRect.top - chartRect.top;
  }

  indicatorPlotWidth(): number {
    this.assertActive();
    return this.chart.timeScale().width();
  }

  drawingPointFromCoordinate(x: number, y: number): DrawingPoint | null {
    this.assertActive();
    const timeScale = this.chart.timeScale();
    const logical = timeScale.coordinateToLogical(x);
    const time = logical === null
      ? timeScale.coordinateToTime(x)
      : drawingTimeForLogicalIndex(logical, this.bars);
    const price = this.priceSeries.coordinateToPrice(y);
    const seconds = typeof time === 'number' ? time : typeof time === 'string' ? timestamp(time) : null;
    if (seconds === null || price === null) return null;
    return { time: new Date(seconds * 1_000).toISOString(), price: price / this.priceScaleMultiplier };
  }

  zoomAtCoordinate(x: number, deltaY: number): void {
    this.assertActive();
    const timeScale = this.chart.timeScale();
    const range = timeScale.getVisibleLogicalRange();
    const anchor = timeScale.coordinateToLogical(x);
    if (!range || anchor === null || !Number.isFinite(deltaY)) return;
    const normalizedDelta = Math.max(-0.35, Math.min(0.35, deltaY / 500));
    const factor = Math.exp(normalizedDelta);
    const nextRange: LogicalRange = {
      from: anchor - (anchor - range.from) * factor,
      to: anchor + (range.to - anchor) * factor,
    };
    timeScale.setVisibleLogicalRange(constrainZoomOutRange(nextRange, this.maxZoomOutRange, anchor));
  }

  panTimeByPixels(deltaX: number): void {
    this.assertActive();
    if (!Number.isFinite(deltaX) || deltaX === 0) return;
    const timeScale = this.chart.timeScale();
    const range = timeScale.getVisibleLogicalRange();
    if (!range) return;

    // Use the current bar spacing instead of converting the range endpoints
    // back to coordinates. Once a drag moves past the loaded data, the chart
    // clamps both out-of-range logical coordinates to the same edge, making
    // that coordinate-based calculation return zero and stopping the drag.
    const pixelsPerLogical = timeScale.options().barSpacing;
    if (!Number.isFinite(pixelsPerLogical) || pixelsPerLogical <= 0) return;
    const logicalDelta = deltaX / pixelsPerLogical;
    timeScale.setVisibleLogicalRange({ from: range.from - logicalDelta, to: range.to - logicalDelta });
  }

  panPriceScaleByPixels(deltaY: number): void {
    this.assertActive();
    this.panPanePriceScaleByPixels(0, deltaY);
  }

  panPriceScaleByPixelsAtCoordinate(y: number, deltaY: number): void {
    this.assertActive();
    if (!Number.isFinite(y)) return;
    this.panPanePriceScaleByPixels(this.paneIndexAtCoordinate(y), deltaY);
  }

  indicatorPaneIdAtCoordinate(y: number): string | null {
    this.assertActive();
    const paneIndex = this.paneIndexAtCoordinate(y);
    return paneIndex > 0 ? this.indicatorPaneIds[paneIndex - 1] ?? null : null;
  }

  private panPanePriceScaleByPixels(paneIndex: number, deltaY: number): void {
    if (!Number.isFinite(deltaY) || deltaY === 0) return;
    const priceScale = this.panePriceScale(paneIndex);
    const range = priceScale?.getVisibleRange();
    const paneHeight = this.chart.panes()[paneIndex]?.getHeight() ?? this.chart.chartElement().getBoundingClientRect().height;
    if (!priceScale || !range || !Number.isFinite(paneHeight) || paneHeight <= 0) return;
    const priceDelta = deltaY / paneHeight * (range.to - range.from);
    priceScale.setAutoScale(false);
    const nextRange = { from: range.from - priceDelta, to: range.to - priceDelta };
    priceScale.setVisibleRange(nextRange);
    const paneId = paneIndex > 0 ? this.indicatorPaneIds[paneIndex - 1] : undefined;
    if (paneId) this.indicatorScaleRanges.set(paneId, nextRange);
    this.notifyViewportChange();
  }

  private paneIndexAtCoordinate(y: number): number {
    if (!Number.isFinite(y)) return 0;
    const chartRect = this.chart.chartElement().getBoundingClientRect();
    for (const [paneIndex, pane] of this.chart.panes().entries()) {
      const paneElement = pane.getHTMLElement();
      if (!paneElement) continue;
      const paneRect = paneElement.getBoundingClientRect();
      const top = paneRect.top - chartRect.top;
      if (y >= top && y <= top + paneRect.height) return paneIndex;
    }
    return 0;
  }

  private panePriceScale(paneIndex: number) {
    if (paneIndex === 0) return this.chart.priceScale(this.priceScaleSide);
    return this.chart.panes()[paneIndex]?.priceScale('right') ?? null;
  }

  private paneValueAtCoordinate(paneIndex: number, y: number): number | null {
    if (paneIndex === 0) return this.priceSeries.coordinateToPrice(y);
    const pane = this.chart.panes()[paneIndex];
    const paneElement = pane?.getHTMLElement();
    if (!paneElement) return null;
    const chartRect = this.chart.chartElement().getBoundingClientRect();
    const paneRect = paneElement.getBoundingClientRect();
    const localY = y - (paneRect.top - chartRect.top);
    for (const [key, series] of this.indicatorSeries) {
      if (this.indicatorSeriesPanes.get(key) === paneIndex) return series.coordinateToPrice(localY);
    }
    return null;
  }

  zoomPriceScaleAtCoordinate(y: number, deltaY: number): void {
    this.assertActive();
    const paneIndex = this.paneIndexAtCoordinate(y);
    const priceScale = this.panePriceScale(paneIndex);
    if (!priceScale) return;
    const range = priceScale.getVisibleRange();
    const anchor = this.paneValueAtCoordinate(paneIndex, y);
    if (!range || anchor === null || !Number.isFinite(deltaY)) return;
    const normalizedDelta = Math.max(-0.35, Math.min(0.35, deltaY / 500));
    const factor = Math.exp(normalizedDelta);
    const nextRange = {
      from: anchor - (anchor - range.from) * factor,
      to: anchor + (range.to - anchor) * factor,
    };
    priceScale.setAutoScale(false);
    priceScale.setVisibleRange(nextRange);
    const paneId = paneIndex > 0 ? this.indicatorPaneIds[paneIndex - 1] : undefined;
    if (paneId) this.indicatorScaleRanges.set(paneId, nextRange);
    this.notifyViewportChange();
  }

  isPriceScaleCoordinate(x: number): boolean {
    this.assertActive();
    const width = this.chart.chartElement().getBoundingClientRect().width;
    const mainPriceScaleWidth = this.chart.priceScale(this.priceScaleSide).width();
    const indicatorPriceScaleWidth = [...new Set(this.indicatorSeriesPanes.values())]
      .filter((paneIndex) => paneIndex > 0)
      .reduce((maxWidth, paneIndex) => Math.max(maxWidth, this.panePriceScale(paneIndex)?.width() ?? 0), 0);
    if (!Number.isFinite(x) || width <= 0) return false;
    if (this.priceScaleSide === 'right' && x >= width - mainPriceScaleWidth) return true;
    if (this.priceScaleSide === 'left' && x <= mainPriceScaleWidth) return true;
    return indicatorPriceScaleWidth > 0 && x >= width - indicatorPriceScaleWidth;
  }

  isMainPriceScaleCoordinate(x: number): boolean {
    this.assertActive();
    const width = this.chart.chartElement().getBoundingClientRect().width;
    const priceScaleWidth = this.chart.priceScale(this.priceScaleSide).width();
    if (!Number.isFinite(x) || width <= 0 || priceScaleWidth <= 0) return false;
    return this.priceScaleSide === 'right' ? x >= width - priceScaleWidth : x <= priceScaleWidth;
  }

  setPriceScaleAutoScale(autoScale: boolean): void {
    this.assertActive();
    this.chart.priceScale(this.priceScaleSide).setAutoScale(autoScale);
    this.notifyViewportChange();
  }

  setPriceScaleMultiplier(multiplier: number): void {
    this.assertActive();
    const nextMultiplier = Number.isFinite(multiplier) && multiplier > 0 ? multiplier : 1;
    if (Math.abs(nextMultiplier - this.priceScaleMultiplier) < 1e-12) return;
    const visibleRange = this.chart.timeScale().getVisibleLogicalRange();
    this.priceScaleMultiplier = nextMultiplier;
    this.setPriceData(this.bars);
    this.setIndicatorOutputs(this.indicatorOutputs);
    this.chart.priceScale(this.priceScaleSide).setAutoScale(true);
    if (visibleRange) this.chart.timeScale().setVisibleLogicalRange(visibleRange);
    this.notifyViewportChange();
  }

  setPriceScaleMode(mode: PriceScaleMode): void {
    this.assertActive();
    this.chart.priceScale(this.priceScaleSide).applyOptions({ mode });
    this.notifyViewportChange();
  }

  setPriceScaleInvert(invertScale: boolean): void {
    this.assertActive();
    this.chart.priceScale(this.priceScaleSide).applyOptions({ invertScale });
    this.notifyViewportChange();
  }

  setPriceScaleSide(side: TradingPriceScaleSide): void {
    this.assertActive();
    this.priceScaleSide = side;
    this.priceSeries.applyOptions({ priceScaleId: side });
    for (const [key, series] of this.indicatorSeries) {
      if (this.indicatorSeriesPanes.get(key) === 0) series.applyOptions({ priceScaleId: side });
    }
    this.chart.applyOptions({
      leftPriceScale: { visible: side === 'left' && this.priceScaleLabelsVisible, borderVisible: this.priceScaleLinesVisible, ticksVisible: this.priceScaleLinesVisible },
      rightPriceScale: { visible: side === 'right' && this.priceScaleLabelsVisible, borderVisible: this.priceScaleLinesVisible, ticksVisible: this.priceScaleLinesVisible },
    });
  }

  setPriceScaleLabelsVisible(visible: boolean): void {
    this.assertActive();
    this.priceScaleLabelsVisible = visible;
    this.chart.applyOptions({
      leftPriceScale: { visible: this.priceScaleSide === 'left' && visible },
      rightPriceScale: { visible: this.priceScaleSide === 'right' && visible },
    });
  }

  setLatestValueLabelVisible(visible: boolean): void {
    this.assertActive();
    this.latestValueLabelVisible = visible;
    this.priceSeries.applyOptions({ lastValueVisible: visible });
  }

  setPriceScaleLinesVisible(visible: boolean): void {
    this.assertActive();
    this.priceScaleLinesVisible = visible;
    this.chart.applyOptions({
      leftPriceScale: { borderVisible: visible, ticksVisible: visible },
      rightPriceScale: { borderVisible: visible, ticksVisible: visible },
    });
  }

  setGridLinesVisible(visible: boolean): void {
    this.assertActive();
    this.gridLinesVisible = visible;
    this.chart.applyOptions({ grid: { vertLines: { visible }, horzLines: { visible } } });
  }

  setScalePriceOnly(enabled: boolean): void {
    this.assertActive();
    this.chart.applyOptions({ handleScale: { axisPressedMouseMove: { time: !enabled, price: true } } });
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

  onIndicatorClick(listener: (selection: TradingIndicatorSelection) => void): () => void {
    this.assertActive();
    const handler = (parameter: MouseEventParams) => {
      const hoveredSeries = parameter.hoveredInfo?.series ?? parameter.hoveredSeries;
      if (!hoveredSeries || !parameter.point) return;
      const selected = [...this.indicatorSeries.entries()].find(([, series]) => series === hoveredSeries);
      if (!selected) return;
      const output = this.indicatorOutputs.find((item) => item.key === selected[0]);
      if (!output) return;
      listener({
        id: selected[0].split(':', 1)[0] as CoreIndicatorId,
        x: parameter.point.x,
        y: parameter.point.y,
      });
    };
    this.chart.subscribeClick(handler);
    return () => this.chart.unsubscribeClick(handler);
  }

  onCrosshair(listener: (point: TradingCrosshairPoint | null) => void): () => void {
    this.assertActive();
    const handler = (parameter: { time?: Time; point?: { x: number; y: number }; seriesData: Map<unknown, unknown> }) => {
      if (parameter.time === undefined || parameter.point === undefined) { listener(null); return; }
      const pointerPrice = this.priceSeries.coordinateToPrice(parameter.point.y);
      if (typeof pointerPrice === 'number' && Number.isFinite(pointerPrice)) {
        listener({ time: parameter.time, price: pointerPrice / this.priceScaleMultiplier });
        return;
      }
      const datum = parameter.seriesData.get(this.priceSeries) as { close?: number; value?: number } | undefined;
      const price = datum?.close ?? datum?.value;
      listener(typeof price === 'number' ? { time: parameter.time, price: price / this.priceScaleMultiplier } : null);
    };
    this.chart.subscribeCrosshairMove(handler);
    return () => this.chart.unsubscribeCrosshairMove(handler);
  }
  setCrosshair(point: TradingCrosshairPoint | null): void { this.assertActive(); if (point === null) this.chart.clearCrosshairPosition(); else this.chart.setCrosshairPosition(point.price * this.priceScaleMultiplier, point.time, this.priceSeries); }
  onVisibleRange(listener: (range: TradingVisibleRange | null) => void): () => void { this.assertActive(); const handler = (range: TradingVisibleRange | null) => listener(range); this.chart.timeScale().subscribeVisibleTimeRangeChange(handler); return () => this.chart.timeScale().unsubscribeVisibleTimeRangeChange(handler); }
  onViewportChange(listener: () => void): () => void {
    this.assertActive();
    const logicalRangeHandler = () => listener();
    const sizeHandler = () => listener();
    this.chart.timeScale().subscribeVisibleLogicalRangeChange(logicalRangeHandler);
    this.chart.timeScale().subscribeSizeChange(sizeHandler);
    this.viewportListeners.add(listener);
    return () => {
      this.chart.timeScale().unsubscribeVisibleLogicalRangeChange(logicalRangeHandler);
      this.chart.timeScale().unsubscribeSizeChange(sizeHandler);
      this.viewportListeners.delete(listener);
    };
  }
  setVisibleRange(range: TradingVisibleRange): void {
    this.assertActive();
    if (this.bars.length === 0 || range.from == null || range.to == null) return;
    const timeScale = this.chart.timeScale();
    if (timeScale.timeToIndex(range.from, true) === null || timeScale.timeToIndex(range.to, true) === null) return;
    timeScale.setVisibleRange(range);
  }
  timeToCoordinate(value: string): number | null {
    this.assertActive();
    const timeScale = this.chart.timeScale();
    const direct = timeScale.timeToCoordinate(timestamp(value));
    if (direct !== null) return direct;
    const logical = drawingLogicalIndexForTime(value, this.bars);
    return logical === null ? null : timeScale.logicalToCoordinate(logical as Logical);
  }
  barIndexAtCoordinate(x: number, barCount: number): number | null {
    this.assertActive();
    const logical = this.chart.timeScale().coordinateToLogical(x);
    if (logical === null || !Number.isFinite(logical)) return null;
    const index = Math.round(logical);
    return index >= 0 && index < barCount ? index : null;
  }
  fitContent(): void {
    this.assertActive();
    const timeScale = this.chart.timeScale();
    timeScale.fitContent();
    this.chart.priceScale(this.priceScaleSide).setAutoScale(true);
    if (this.bars.length > 0) {
      const range = {
        from: -0.5,
        to: this.bars.length - 0.5 + this.rightOffset,
      };
      timeScale.setVisibleLogicalRange(range);
      this.maxZoomOutRange = range;
      return;
    }
    const range = timeScale.getVisibleLogicalRange();
    if (range) this.maxZoomOutRange = { from: range.from, to: range.to };
  }
  setRightOffset(offset: number): void {
    this.assertActive();
    this.rightOffset = Math.max(0, Math.min(100, Math.round(offset)));
    this.chart.timeScale().applyOptions({ rightOffset: this.rightOffset });
  }
  scrollToLatest(): void { this.assertActive(); this.chart.timeScale().scrollToRealTime(); }
  api(): IChartApi { this.assertActive(); return this.chart; }
  destroy(): void { if (this.destroyed) return; this.restoreFullscreenPaneHeights(); this.destroyed = true; this.revisions.clear(); this.bars = []; this.indicatorOutputs = []; this.indicatorSeries.clear(); this.viewportListeners.clear(); this.chart.remove(); }
  private notifyViewportChange(): void { for (const listener of this.viewportListeners) listener(); }
  private assertActive(): void { if (this.destroyed) throw new Error('Trading chart adapter is disposed'); }
}
