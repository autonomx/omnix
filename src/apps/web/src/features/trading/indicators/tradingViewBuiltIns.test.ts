import { describe, expect, it } from 'vitest';
import type { MarketBar } from '../tradingTypes';
import {
  TRADINGVIEW_BUILTIN_DEFINITIONS,
  calculateTradingViewBuiltInOutputs,
  isTradingViewBuiltInId,
} from './tradingViewBuiltIns';

function fixtureBars(count = 720): MarketBar[] {
  return Array.from({ length: count }, (_, index) => {
    const trend = 100 + index * 0.035;
    const wave = Math.sin(index / 9) * 4 + Math.sin(index / 29) * 7;
    const close = trend + wave;
    const open = close - Math.sin(index / 3) * 0.8;
    const high = Math.max(open, close) + 1.5 + (index % 5) * 0.08;
    const low = Math.min(open, close) - 1.4 - (index % 4) * 0.07;
    return {
      instrument_id: 'equity:NASDAQ:NVDA',
      interval: '1d',
      start_time: new Date(Date.UTC(2024, 0, index + 1)).toISOString(),
      end_time: new Date(Date.UTC(2024, 0, index + 2)).toISOString(),
      open: String(open),
      high: String(high),
      low: String(low),
      close: String(close),
      volume: String(1_000_000 + (index % 31) * 42_000 + index * 500),
      is_final: true,
      adjustment_mode: 'raw',
      session: 'regular',
      provider: 'fixture',
      ingestion_revision: 1,
      received_at: new Date().toISOString(),
    };
  });
}

describe('TradingView built-in indicator catalog', () => {
  it('mirrors the complete unique TradingView built-in support-folder catalog', () => {
    expect(TRADINGVIEW_BUILTIN_DEFINITIONS).toHaveLength(208);
    expect(new Set(TRADINGVIEW_BUILTIN_DEFINITIONS.map((definition) => definition.name)).size).toBe(208);
    expect(TRADINGVIEW_BUILTIN_DEFINITIONS.some((definition) => definition.name === '1 year active supply %')).toBe(true);
    expect(TRADINGVIEW_BUILTIN_DEFINITIONS.some((definition) => definition.name === 'Zig Zag')).toBe(true);
  });

  it('marks feed-dependent studies unavailable instead of fabricating their data', () => {
    const openInterest = TRADINGVIEW_BUILTIN_DEFINITIONS.find((definition) => definition.name === 'Open Interest');
    const analystForecast = TRADINGVIEW_BUILTIN_DEFINITIONS.find((definition) => definition.name === 'Analyst price forecast');
    expect(openInterest).toMatchObject({ available: false });
    expect(analystForecast).toMatchObject({ available: false });
    expect(openInterest?.requirement).toMatch(/data|feed|series/i);
  });

  it('calculates finite output for the OHLCV-backed catalog', () => {
    const bars = fixtureBars();
    const available = TRADINGVIEW_BUILTIN_DEFINITIONS.filter((definition) => definition.available && isTradingViewBuiltInId(definition.id));
    expect(available.length).toBeGreaterThan(70);
    for (const definition of available) {
      const outputs = calculateTradingViewBuiltInOutputs(bars, {
        id: definition.id,
        period: definition.defaultPeriod,
      });
      expect(outputs, definition.name).not.toHaveLength(0);
      expect(outputs.flatMap((output) => output.points).every((point) => Number.isFinite(point.value)), definition.name).toBe(true);
    }
  });

  it('keeps Trend Strength Index in its documented -1 to +1 range', () => {
    const definition = TRADINGVIEW_BUILTIN_DEFINITIONS.find((item) => item.name === 'Trend Strength Index');
    expect(definition).toBeDefined();
    const points = calculateTradingViewBuiltInOutputs(fixtureBars(160), {
      id: definition!.id,
      period: definition!.defaultPeriod,
    }).flatMap((output) => output.points);
    expect(points.length).toBeGreaterThan(0);
    expect(points.every((point) => point.value >= -1 && point.value <= 1)).toBe(true);
  });
});
