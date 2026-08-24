import { useCallback, useLayoutEffect, useMemo, useRef } from 'react';
import type { TradingChartAdapter, DrawingCoordinate } from './chart/chartAdapter';
import { indicatorPaneScale, type CoreIndicatorId, type IndicatorOutput } from './indicators/coreIndicators';
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

type PaneBand = {
  id: string;
  key: string;
  scale: NonNullable<ReturnType<typeof indicatorPaneScale>>;
  color: string;
};

export function TradingIndicatorBackgroundOverlay({ adapter, outputs }: TradingIndicatorBackgroundOverlayProps) {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const groups = useMemo(() => {
    const grouped = new Map<string, IndicatorOutput[]>();
    for (const output of outputs) {
      if (output.kind !== 'line' || output.backgroundVisible === false) continue;
      const group = grouped.get(outputGroupKey(output.key)) ?? [];
      group.push(output);
      grouped.set(outputGroupKey(output.key), group);
    }
    return grouped;
  }, [outputs]);
  const paneBands = useMemo<PaneBand[]>(() => (
    [...groups.entries()].flatMap(([id, group]) => {
      const output = group.find((item) => item.pane === 1);
      const scale = indicatorPaneScale(id as CoreIndicatorId);
      if (!output || !scale?.band) return [];
      return [{ id, key: output.key, scale, color: output.backgroundColor ?? scale.band.color }];
    })
  ), [groups]);

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
    for (const bandElement of svg.querySelectorAll<SVGGElement>('[data-indicator-pane-band]')) {
      const id = bandElement.dataset.indicatorPaneBand;
      const band = paneBands.find((item) => item.id === id);
      if (!band?.scale.band) continue;
      const upper = adapter.indicatorValueToCoordinate(band.key, band.scale.band.to);
      const lower = adapter.indicatorValueToCoordinate(band.key, band.scale.band.from);
      if (upper === null || lower === null) continue;
      const width = adapter.indicatorPlotWidth();
      const rect = bandElement.querySelector<SVGRectElement>('[data-indicator-pane-band-fill]');
      if (rect) {
        rect.setAttribute('width', String(width));
        rect.setAttribute('y', String(Math.min(upper, lower)));
        rect.setAttribute('height', String(Math.abs(lower - upper)));
      }
      for (const line of bandElement.querySelectorAll<SVGLineElement>('[data-indicator-reference-line]')) {
        const value = Number(line.dataset.indicatorReferenceLine);
        const y = adapter.indicatorValueToCoordinate(band.key, value);
        if (y === null) continue;
        line.setAttribute('x2', String(width));
        line.setAttribute('y1', String(y));
        line.setAttribute('y2', String(y));
      }
    }
  }, [adapter, groups, paneBands]);

  useLayoutEffect(() => {
    refresh();
    return adapter.onViewportChange(refresh);
  }, [adapter, refresh]);

  return (
    <svg ref={svgRef} className="trading-indicator-background-overlay" aria-hidden="true">
      {[...groups.entries()].filter(([, group]) => group.some((output) => output.pane === 0)).map(([key, group]) => {
        const boundaries = boundaryOutputs(group);
        if (!boundaries) return null;
        const [upper, lower] = boundaries;
        const points = bandPolygon(adapter, upper, lower);
        return <polygon key={key} data-indicator-background={key} points={points ?? ''} fill={upper.backgroundColor ?? lower.backgroundColor ?? '#74c0fc'} fillOpacity="0.2" />;
      })}
      {paneBands.map((band) => (
        <g key={band.id} data-indicator-pane-band={band.id}>
          <rect data-indicator-pane-band-fill="true" x="0" y="0" width="0" height="0" fill={band.color} fillOpacity="0.2" />
          {band.scale.levels.map((level) => (
            <line
              key={level.value}
              data-indicator-reference-line={String(level.value)}
              x1="0"
              x2="0"
              y1="0"
              y2="0"
              stroke="rgba(109, 126, 143, .72)"
              strokeDasharray={level.lineStyle === 'dotted' ? '2 4' : '6 5'}
              strokeWidth="1"
            />
          ))}
        </g>
      ))}
    </svg>
  );
}
