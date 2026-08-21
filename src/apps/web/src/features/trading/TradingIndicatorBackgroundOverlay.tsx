import { useCallback, useLayoutEffect, useMemo, useRef } from 'react';
import type { TradingChartAdapter, DrawingCoordinate } from './chart/chartAdapter';
import type { IndicatorOutput } from './indicators/coreIndicators';
import './TradingIndicatorBackgroundOverlay.css';

type TradingIndicatorBackgroundOverlayProps = {
  adapter: TradingChartAdapter;
  outputs: readonly IndicatorOutput[];
};

function outputGroupKey(key: string): string {
  const parts = key.split(':');
  return parts.length > 1 ? parts.slice(0, -1).join(':') : key;
}

function boundaryOutputs(outputs: readonly IndicatorOutput[]): [IndicatorOutput, IndicatorOutput] | null {
  if (outputs.length < 2) return null;
  if (outputs.length === 2) return [outputs[0], outputs[1]];
  const upper = outputs.find((output) => output.key.endsWith(':upper'));
  const lower = outputs.find((output) => output.key.endsWith(':lower'));
  return upper && lower ? [upper, lower] : [outputs[0], outputs[outputs.length - 1]];
}

function bandPolygon(
  adapter: TradingChartAdapter,
  upper: IndicatorOutput,
  lower: IndicatorOutput,
): string | null {
  const lowerByTime = new Map(lower.points.map((point) => [point.time, point]));
  const first: DrawingCoordinate[] = [];
  const second: DrawingCoordinate[] = [];
  for (const point of upper.points) {
    const matchingPoint = lowerByTime.get(point.time);
    if (!matchingPoint) continue;
    const firstCoordinate = adapter.indicatorPointToCoordinate(upper.key, point);
    const secondCoordinate = adapter.indicatorPointToCoordinate(lower.key, matchingPoint);
    if (!firstCoordinate || !secondCoordinate) continue;
    first.push(firstCoordinate);
    second.push(secondCoordinate);
  }
  if (first.length < 2) return null;
  return [...first, ...second.reverse()].map(({ x, y }) => `${x},${y}`).join(' ');
}

export function TradingIndicatorBackgroundOverlay({ adapter, outputs }: TradingIndicatorBackgroundOverlayProps) {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const groups = useMemo(() => {
    const grouped = new Map<string, IndicatorOutput[]>();
    for (const output of outputs) {
      if (output.pane !== 0 || output.kind !== 'line' || output.backgroundVisible === false) continue;
      const group = grouped.get(outputGroupKey(output.key)) ?? [];
      group.push(output);
      grouped.set(outputGroupKey(output.key), group);
    }
    return grouped;
  }, [outputs]);

  const refresh = useCallback(() => {
    const svg = svgRef.current;
    if (!svg) return;
    for (const polygon of svg.querySelectorAll<SVGPolygonElement>('[data-indicator-background]')) {
      const key = polygon.dataset.indicatorBackground;
      const group = key ? groups.get(key) : undefined;
      const boundaries = group ? boundaryOutputs(group) : null;
      if (!boundaries) {
        polygon.setAttribute('points', '');
        continue;
      }
      polygon.setAttribute('points', bandPolygon(adapter, boundaries[0], boundaries[1]) ?? '');
    }
  }, [adapter, groups]);

  useLayoutEffect(() => {
    refresh();
    return adapter.onViewportChange(refresh);
  }, [adapter, refresh]);

  return (
    <svg ref={svgRef} className="trading-indicator-background-overlay" aria-hidden="true">
      {[...groups.entries()].map(([key, group]) => {
        const boundaries = boundaryOutputs(group);
        if (!boundaries) return null;
        const [upper, lower] = boundaries;
        const points = bandPolygon(adapter, upper, lower);
        return <polygon key={key} data-indicator-background={key} points={points ?? ''} fill={upper.backgroundColor ?? lower.backgroundColor ?? '#74c0fc'} fillOpacity="0.2" />;
      })}
    </svg>
  );
}
