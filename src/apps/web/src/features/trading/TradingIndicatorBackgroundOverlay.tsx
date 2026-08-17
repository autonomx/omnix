import { useEffect, useState } from 'react';
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
  const [, setRevision] = useState(0);

  useEffect(() => {
    let frame: number | null = null;
    const invalidate = () => {
      if (frame !== null) return;
      frame = window.requestAnimationFrame(() => {
        frame = null;
        setRevision((value) => value + 1);
      });
    };
    invalidate();
    const unsubscribe = adapter.onViewportChange(invalidate);
    return () => {
      unsubscribe();
      if (frame !== null) window.cancelAnimationFrame(frame);
    };
  }, [adapter, outputs]);

  const groups = new Map<string, IndicatorOutput[]>();
  for (const output of outputs) {
    if (output.pane !== 0 || output.kind !== 'line' || output.backgroundVisible === false) continue;
    const group = groups.get(outputGroupKey(output.key)) ?? [];
    group.push(output);
    groups.set(outputGroupKey(output.key), group);
  }

  return (
    <svg className="trading-indicator-background-overlay" aria-hidden="true">
      {[...groups.entries()].map(([key, group]) => {
        const boundaries = boundaryOutputs(group);
        if (!boundaries) return null;
        const [upper, lower] = boundaries;
        const points = bandPolygon(adapter, upper, lower);
        return points ? <polygon key={key} points={points} fill={upper.backgroundColor ?? lower.backgroundColor ?? '#74c0fc'} fillOpacity="0.2" /> : null;
      })}
    </svg>
  );
}
