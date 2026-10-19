import type { UTCTimestamp } from 'lightweight-charts';

/** A time series to draw: UTC seconds and values, in ascending time order. */
export type TimeSeriesInput = {
  kind: 'line' | 'area';
  series: Array<{ name: string; color: string; points: ReadonlyArray<readonly [number, number]> }>;
  textColor: string;
  gridColor: string;
  intraday: boolean;
  formatValue: (value: number) => string;
};

/**
 * Chat's own lightweight-charts wrapper for time-series blocks (no trading chart internals).
 * The library is loaded on first use; the returned function removes the chart.
 */
export async function mountTimeSeriesChart(container: HTMLElement, input: TimeSeriesInput): Promise<() => void> {
  const { AreaSeries, LineSeries, createChart } = await import('lightweight-charts');
  const chart = createChart(container, {
    autoSize: true,
    layout: { background: { color: 'transparent' }, textColor: input.textColor, attributionLogo: false },
    grid: { vertLines: { visible: false }, horzLines: { color: input.gridColor } },
    rightPriceScale: { borderVisible: false },
    timeScale: { borderVisible: false, timeVisible: input.intraday, secondsVisible: false, fixLeftEdge: true, fixRightEdge: true },
    localization: { priceFormatter: input.formatValue },
    handleScroll: false,
    handleScale: false,
  });
  for (const item of input.series) {
    const data = item.points.map(([time, value]) => ({ time: time as UTCTimestamp, value }));
    const series = input.kind === 'area'
      ? chart.addSeries(AreaSeries, { lineColor: item.color, topColor: withAlpha(item.color, 0.28), bottomColor: withAlpha(item.color, 0.02), lineWidth: 2, priceLineVisible: false })
      : chart.addSeries(LineSeries, { color: item.color, lineWidth: 2, priceLineVisible: false });
    series.setData(data);
  }
  chart.timeScale().fitContent();
  return () => chart.remove();
}

/** `rgb(r, g, b)` -> `rgba(r, g, b, alpha)`; other colour forms are returned unchanged. */
function withAlpha(color: string, alpha: number): string {
  const match = color.match(/^rgba?\(([^,]+),([^,]+),([^,)]+)/);
  return match ? `rgba(${match[1].trim()}, ${match[2].trim()}, ${match[3].trim()}, ${alpha})` : color;
}
