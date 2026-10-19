import type { ChartBlock } from './schema';

type NumberFormat = ChartBlock['y']['format'];

const plain = new Intl.NumberFormat('en-US', { maximumFractionDigits: 4 });
const compact = new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 1 });

/** A chart value as the block's y-axis format says (percent values are already in percent). */
export function formatChartValue(value: number, format: NumberFormat = 'number'): string {
  if (!Number.isFinite(value)) return '';
  if (format === 'percent') return `${plain.format(value)}%`;
  if (format === 'currency') return value < 0 ? `-$${plain.format(-value)}` : `$${plain.format(value)}`;
  if (format === 'compact') return compact.format(value);
  return plain.format(value);
}

/** An x value: a UTC date (or date and time when intraday) for time axes, the label for categories. */
export function formatChartX(value: number | string, axis: ChartBlock['x']['type'], intraday = false): string {
  if (axis !== 'time' || typeof value !== 'number') return String(value);
  const iso = new Date(value * 1000).toISOString();
  return intraday ? `${iso.slice(0, 10)} ${iso.slice(11, 16)}` : iso.slice(0, 10);
}

/** Whether a time series has points closer together than a day. */
export function isIntraday(points: ReadonlyArray<readonly [number | string, number]>): boolean {
  for (let index = 1; index < points.length; index += 1) {
    const step = Number(points[index][0]) - Number(points[index - 1][0]);
    if (step > 0 && step < 86_400) return true;
  }
  return false;
}

/** The series colour tokens, in order; ChatGenerativeUi.css defines them from theme variables. */
export const SERIES_COLOR_VARIABLES = ['--gui-series-1', '--gui-series-2', '--gui-series-3', '--gui-series-4', '--gui-series-5', '--gui-series-6'] as const;

/**
 * Concrete colours for canvas drawing: theme variables can hold color-mix() or var() chains,
 * so each is resolved by a probe element inside the chart's container.
 */
export function resolveCssColors(container: HTMLElement, cssValues: readonly string[]): string[] {
  const probe = document.createElement('span');
  probe.style.display = 'none';
  container.appendChild(probe);
  try {
    return cssValues.map((value) => {
      probe.style.color = '';
      probe.style.color = value;
      return getComputedStyle(probe).color || 'currentColor';
    });
  } finally {
    probe.remove();
  }
}
