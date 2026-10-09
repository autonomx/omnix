import { describe, expect, it } from 'vitest';
import { fixture } from '../../../test/fixture';
import { alertIndicatorChoices } from '../alertIndicatorSources';
import { parseIndicatorInstances } from '../persistence/workspaceDocument';
import type { MarketBar } from '../tradingTypes';
import { indicatorOutputs, type CoreIndicatorInstance, type IndicatorOutput } from './coreIndicators';
import { calculateWithSources, indicatorSourceChoices, orderBySources, sourceBars } from './indicatorSources';

const bars: MarketBar[] = Array.from({ length: 60 }, (_, i) => fixture({
  instrument_id: 'x', interval: '1h', start_time: new Date(Date.UTC(2026, 0, 5, i)).toISOString(), end_time: new Date(Date.UTC(2026, 0, 5, i + 1)).toISOString(),
  open: String(100 + Math.sin(i / 3) * 5), high: String(106 + Math.sin(i / 3) * 5), low: String(94 + Math.sin(i / 3) * 5), close: String(101 + Math.sin(i / 3) * 5),
  volume: String(1000 + i), is_final: true, adjustment_mode: 'raw', session: '24x7', provider: 'binance', ingestion_revision: 1, received_at: new Date(Date.UTC(2026, 0, 5, i + 1)).toISOString(),
}));
const rsi: CoreIndicatorInstance = { id: 'rsi', period: 14, enabled: true };
const smaOfRsi: CoreIndicatorInstance = { id: 'sma', period: 5, enabled: true, source: { indicatorId: 'rsi', output: 'rsi:14' } };
const raw = (source: readonly MarketBar[], indicator: CoreIndicatorInstance): IndicatorOutput[] => indicatorOutputs(source, indicator);

describe('indicator on indicator (TVP-6.5)', () => {
  it('turns an output into bars whose prices are its values', () => {
    const points = [{ time: bars[1].start_time, value: 42 }, { time: bars[3].start_time, value: Number.NaN }];
    expect(sourceBars(bars, points)).toEqual([{ ...bars[1], open: '42', high: '42', low: '42', close: '42' }]);
  });

  it('computes sources first and drops sources it cannot use: cycles, itself, disabled, nested, or a target without one', () => {
    expect(orderBySources([smaOfRsi, rsi]).map((item) => item.id)).toEqual(['rsi', 'sma']);
    const emaOfSma: CoreIndicatorInstance = { id: 'ema', period: 3, enabled: true, source: { indicatorId: 'sma', output: 'sma:5' } };
    const self: CoreIndicatorInstance = { id: 'ema', period: 3, enabled: true, source: { indicatorId: 'ema', output: 'ema:3' } };
    const atr: CoreIndicatorInstance = { id: 'atr', period: 14, enabled: true, source: { indicatorId: 'rsi', output: 'rsi:14' } };
    expect(orderBySources([smaOfRsi, rsi, emaOfSma]).find((item) => item.id === 'ema')?.source).toBeNull();
    expect(orderBySources([self])[0].source).toBeNull();
    expect(orderBySources([atr, rsi]).find((item) => item.id === 'atr')?.source).toBeNull();
    expect(orderBySources([smaOfRsi, { ...rsi, enabled: false }]).find((item) => item.id === 'sma')?.source).toBeNull();
  });

  it('draws an indicator on a pane indicator in that pane, and equals the indicator of the source series', () => {
    const outputs = calculateWithSources(bars, [smaOfRsi, rsi], raw);
    const sma = outputs.find((output) => output.key === 'sma:5')!;
    expect(sma).toMatchObject({ pane: 1, paneOf: 'rsi' });
    const rsiOutput = outputs.find((output) => output.key === 'rsi:14')!;
    const expected = indicatorOutputs(sourceBars(bars, rsiOutput.points), { id: 'sma', period: 5, enabled: true })[0];
    expect(sma.points).toEqual(expected.points);
    // SMA of an SMA stays on the price pane.
    const smaOfSma = calculateWithSources(bars, [{ id: 'ema', period: 3, enabled: true, source: { indicatorId: 'sma', output: 'sma:5' } }, { id: 'sma', period: 5, enabled: true }], raw);
    expect(smaOfSma.find((output) => output.key.startsWith('ema'))?.pane).toBe(0);
  });

  it('reads a hidden source, and its first line when the source key changed', () => {
    const hidden = calculateWithSources(bars, [smaOfRsi, { ...rsi, visible: false }], raw, (outputs, indicator) => (indicator.visible === false ? [] : outputs));
    expect(hidden.map((output) => output.key)).toEqual(['sma:5']);
    const renamed = calculateWithSources(bars, [smaOfRsi, { ...rsi, period: 21 }], raw);
    expect(renamed.find((output) => output.key === 'sma:5')?.points.length).toBeGreaterThan(0);
  });

  it('offers the other indicators lines as sources to indicators that take one', () => {
    const outputs = calculateWithSources(bars, [rsi, { id: 'sma', period: 5, enabled: true }], raw);
    expect(indicatorSourceChoices({ id: 'sma', period: 5, enabled: true }, [rsi, { id: 'sma', period: 5, enabled: true }], outputs).map((choice) => choice.value)).toEqual(['rsi:14']);
    expect(indicatorSourceChoices({ id: 'atr', period: 14, enabled: true }, [rsi], outputs)).toEqual([]);
  });

  it('alerts carry the source indicator, and grey out a source the server cannot evaluate', () => {
    const outputs = calculateWithSources(bars, [smaOfRsi, rsi], raw);
    const [smaChoice] = alertIndicatorChoices([smaOfRsi, rsi], outputs, new Set(['sma', 'rsi']));
    expect(smaChoice.unavailable).toBeUndefined();
    expect(smaChoice.inputs.source).toMatchObject({ indicator_id: 'rsi', output: 'rsi:14', inputs: { period: 14 } });
    const [greyed] = alertIndicatorChoices([smaOfRsi, rsi], outputs, new Set(['sma']));
    expect(greyed.unavailable).toMatch(/source indicator/);
  });

  it('keeps the source in saved workspaces and rejects a malformed one', () => {
    expect(parseIndicatorInstances([smaOfRsi])?.[0].source).toEqual({ indicatorId: 'rsi', output: 'rsi:14' });
    expect(parseIndicatorInstances([{ ...smaOfRsi, source: { indicatorId: 3 } }])).toBeNull();
  });
});
