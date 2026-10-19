import { useEffect, useId, useMemo, useRef, useState } from 'react';
import { mountTimeSeriesChart } from '../chatChartAdapter';
import { SERIES_COLOR_VARIABLES, formatChartValue, formatChartX, isIntraday, resolveCssColors } from '../format';
import type { ChartBlock } from '../schema';
import { ProvenanceBadge } from './ProvenanceBadge';

type Point = readonly [number | string, number];

/** A line, area or bar chart of model-supplied (or bound) data, with a data table toggle. */
export function ChartBlockView({ block, summary }: { block: ChartBlock; summary: string }) {
  const [showData, setShowData] = useState(false);
  const [canvasFailed, setCanvasFailed] = useState(false);
  const tableId = useId();
  const timeSeries = block.x.type === 'time' && block.kind !== 'bar';
  return (
    <section className="gui-block gui-chart" data-size={block.size} aria-label={block.title ?? 'Chart'}>
      {block.title || block.bindings.length || block.provenance === 'model' ? (
        <header className="gui-block-header">
          {block.title ? <h4>{block.title}</h4> : null}
          <ProvenanceBadge block={block} />
        </header>
      ) : null}
      {timeSeries && !canvasFailed
        ? <TimeSeriesPlot block={block} summary={summary} onFailed={setCanvasFailed} />
        : <CategoryPlot block={block} summary={summary} />}
      <div className="gui-chart-footer">
        {block.series.length > 1 ? (
          <ul className="gui-chart-legend" aria-label="Series">
            {block.series.map((series, index) => (
              <li key={series.name} data-series={index % SERIES_COLOR_VARIABLES.length}><span aria-hidden="true" />{series.name}</li>
            ))}
          </ul>
        ) : <span />}
        <button type="button" className="gui-link-button" aria-expanded={showData || canvasFailed} aria-controls={tableId} onClick={() => setShowData((value) => !value)} disabled={canvasFailed}>
          {showData || canvasFailed ? 'Hide data' : 'Show data'}
        </button>
      </div>
      {showData || canvasFailed ? <ChartDataTable id={tableId} block={block} /> : null}
    </section>
  );
}

function TimeSeriesPlot({ block, summary, onFailed }: { block: ChartBlock; summary: string; onFailed: (failed: boolean) => void }) {
  const hostRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const host = hostRef.current;
    if (!host) return undefined;
    let dispose: (() => void) | null = null;
    let cancelled = false;
    const colors = resolveCssColors(host, [
      ...SERIES_COLOR_VARIABLES.map((name) => `var(${name})`),
      'var(--omnix-muted)',
      'var(--omnix-border)',
    ]);
    mountTimeSeriesChart(host, {
      kind: block.kind === 'area' ? 'area' : 'line',
      series: block.series.map((series, index) => ({
        name: series.name,
        color: colors[index % SERIES_COLOR_VARIABLES.length],
        points: series.points.map(([x, y]) => [Number(x), y] as const),
      })),
      textColor: colors[SERIES_COLOR_VARIABLES.length],
      gridColor: colors[SERIES_COLOR_VARIABLES.length + 1],
      intraday: block.series.some((series) => isIntraday(series.points)),
      formatValue: (value) => formatChartValue(value, block.y.format),
    }).then((remove) => {
      if (cancelled) remove();
      else dispose = remove;
    }).catch(() => {
      if (!cancelled) onFailed(true);
    });
    return () => {
      cancelled = true;
      dispose?.();
    };
  }, [block, onFailed]);
  return <div ref={hostRef} className="gui-chart-plot gui-chart-canvas" role="img" aria-label={summary} />;
}

function CategoryPlot({ block, summary }: { block: ChartBlock; summary: string }) {
  const intraday = block.series.some((series) => isIntraday(series.points));
  const { categories, lookup, minimum, maximum } = useMemo(() => categoryLayout(block), [block]);
  const span = maximum - minimum || 1;
  const y = (value: number) => 100 - ((value - minimum) / span) * 100;
  const ticks = [0, 1, 2, 3].map((step) => minimum + (span * step) / 3);
  const step = Math.max(1, Math.ceil(categories.length / 8));
  const width = 100 / Math.max(1, categories.length);
  const barWidth = (width * 0.72) / block.series.length;
  return (
    <div className="gui-chart-plot gui-chart-svg" role="img" aria-label={summary}>
      <div className="gui-chart-yaxis" aria-hidden="true">
        {ticks.map((tick) => <span key={tick} style={{ bottom: `${((tick - minimum) / span) * 100}%` }}>{formatChartValue(tick, block.y.format)}</span>)}
      </div>
      <svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true" focusable="false">
        {ticks.map((tick) => <line key={tick} className="gui-chart-grid" x1="0" x2="100" y1={y(tick)} y2={y(tick)} vectorEffect="non-scaling-stroke" />)}
        {block.series.map((series, seriesIndex) => {
          const values = lookup[seriesIndex];
          const color = seriesIndex % SERIES_COLOR_VARIABLES.length;
          if (block.kind === 'bar') {
            const base = y(Math.max(minimum, Math.min(0, maximum)));
            return categories.map((category, index) => {
              const value = values.get(category);
              if (value === undefined) return null;
              const top = Math.min(base, y(value));
              return <rect key={`${series.name}:${category}`} className="gui-chart-bar" data-series={color} x={index * width + width * 0.14 + seriesIndex * barWidth} y={top} width={barWidth} height={Math.max(0.5, Math.abs(base - y(value)))} />;
            });
          }
          const points = categories.flatMap((category, index) => {
            const value = values.get(category);
            return value === undefined ? [] : [`${index * width + width / 2},${y(value)}`];
          }).join(' ');
          return <polyline key={series.name} className="gui-chart-line" data-series={color} data-area={block.kind === 'area' ? 'true' : undefined} points={points} vectorEffect="non-scaling-stroke" />;
        })}
      </svg>
      <div className="gui-chart-xaxis" aria-hidden="true" style={{ gridTemplateColumns: `repeat(${categories.length}, minmax(0, 1fr))` }}>
        {categories.map((category, index) => <span key={category}>{index % step === 0 ? formatChartX(categoryValue(category), block.x.type, intraday) : ''}</span>)}
      </div>
    </div>
  );
}

function categoryValue(key: string): number | string {
  return key.startsWith('t:') ? Number(key.slice(2)) : key.slice(2);
}

function categoryKey(value: number | string): string {
  return typeof value === 'number' ? `t:${value}` : `c:${value}`;
}

function categoryLayout(block: ChartBlock) {
  const ordered = new Map<string, number | string>();
  const lookup = block.series.map((series) => new Map(series.points.map(([x, value]) => {
    const key = categoryKey(x);
    if (!ordered.has(key)) ordered.set(key, x);
    return [key, value] as const;
  })));
  let categories = [...ordered.keys()];
  if (block.x.type === 'time') categories = categories.sort((a, b) => Number(ordered.get(a)) - Number(ordered.get(b)));
  const values = block.series.flatMap((series) => series.points.map(([, value]) => value));
  let minimum = Math.min(...values);
  let maximum = Math.max(...values);
  if (block.kind === 'bar') {
    minimum = Math.min(0, minimum);
    maximum = Math.max(0, maximum);
  }
  return { categories, lookup, minimum, maximum };
}

/** Every value in a table: the chart's accessible equivalent. */
export function ChartDataTable({ id, block }: { id: string; block: ChartBlock }) {
  const intraday = block.series.some((series) => isIntraday(series.points));
  const rows = useMemo(() => {
    const keys = new Map<string, Point[0]>();
    for (const series of block.series) for (const [x] of series.points) keys.set(categoryKey(x), x);
    const ordered = [...keys.values()];
    if (block.x.type === 'time') ordered.sort((a, b) => Number(a) - Number(b));
    const lookup = block.series.map((series) => new Map(series.points.map(([x, value]) => [categoryKey(x), value])));
    return ordered.map((x) => ({ x, values: lookup.map((values) => values.get(categoryKey(x))) }));
  }, [block]);
  return (
    <div className="gui-chart-table" id={id} role="region" aria-label={`${block.title ?? 'Chart'} data`} tabIndex={0}>
      <table>
        <caption className="gui-visually-hidden">{block.title ?? 'Chart'} data</caption>
        <thead>
          <tr>
            <th scope="col">{block.x.label ?? (block.x.type === 'time' ? 'Date' : 'Category')}</th>
            {block.series.map((series) => <th scope="col" key={series.name}>{series.name}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={String(row.x)}>
              <th scope="row">{formatChartX(row.x, block.x.type, intraday)}</th>
              {row.values.map((value, index) => <td key={block.series[index].name}>{value === undefined ? '' : formatChartValue(value, block.y.format)}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
