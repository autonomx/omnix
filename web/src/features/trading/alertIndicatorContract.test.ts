// The alert indicator contract (TVP-1.3): for each indicator the server evaluates, the inputs a chart's default
// instance sends and the output lines it draws. src/tests/trading/test_trading_alert_indicator_contract.py checks
// these against the server, so a chart line offered in the alert dialog is one the server can alert on.
import { readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { alertIndicatorChoices } from './alertIndicatorSources';
import { indicatorOutputs, type CoreIndicatorId, type IndicatorOutput } from './indicators/coreIndicators';
import { calculateTradingViewBuiltInOutputs, isTradingViewBuiltInId } from './indicators/tradingViewBuiltIns';
import { newIndicatorInstance } from './tradingStore';
import type { MarketBar } from './tradingTypes';

// Tests run from the web package directory.
const FIXTURE = resolve(process.cwd(), 'src/features/trading/indicators/fixtures/alertIndicatorContract.json');

function bars(count = 400): MarketBar[] {
  const start = Date.parse('2026-01-02T14:30:00Z');
  return Array.from({ length: count }, (_, index) => {
    const close = 100 + 10 * Math.sin(index / 9) + index * 0.05;
    const time = new Date(start + index * 60_000).toISOString();
    return {
      instrument_id: 'equity:NASDAQ:TEST', interval: '1m', start_time: time, end_time: new Date(start + (index + 1) * 60_000).toISOString(),
      open: String(close - 0.4), high: String(close + 1), low: String(close - 1), close: String(close), volume: String(1000 + (index % 17) * 50),
      is_final: true, provider: 'fixture', received_at: time,
    } as MarketBar;
  });
}

describe('alert indicator contract (TVP-1.3)', () => {
  it('records each server indicator a chart offers, with its default inputs and lines', () => {
    const fixture = JSON.parse(readFileSync(FIXTURE, 'utf-8')) as { note: string; ids: string[]; entries: unknown[] };
    const series = bars();
    const serverIds = new Set(fixture.ids);
    const entries = fixture.ids.flatMap((id) => {
      let instance;
      try {
        instance = newIndicatorInstance(id as CoreIndicatorId);
      } catch {
        return [];
      }
      // As the chart computes them (indicatorScheduler.ts).
      const outputs = isTradingViewBuiltInId(id)
        ? calculateTradingViewBuiltInOutputs(series, { ...instance, id }, {}) as IndicatorOutput[]
        : indicatorOutputs(series, instance);
      const [choice] = alertIndicatorChoices([instance], outputs, serverIds);
      return choice && !choice.unavailable ? [{ id, inputs: choice.inputs, outputs: choice.outputs.map((output) => output.key) }] : [];
    });
    if (process.env.UPDATE_ALERT_CONTRACT) writeFileSync(FIXTURE, `${JSON.stringify({ ...fixture, entries }, null, 1)}\n`);
    expect(entries).toEqual(JSON.parse(readFileSync(FIXTURE, 'utf-8')).entries);
    expect(entries.length).toBeGreaterThan(50);
  });
});
