import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AlertIndicatorPicker } from './AlertIndicatorPicker';
import { alertIndicatorChoices, defaultIndicatorSelection, withChartIndicatorCondition } from './alertIndicatorSources';
import type { CoreIndicatorInstance, IndicatorOutput } from './indicators/coreIndicators';
import { chartAlertCreateInput } from './tradingChartAlerts';

afterEach(cleanup);

const line = (key: string, title: string) => ({ key, title, pane: 1, kind: 'line', points: [] }) as unknown as IndicatorOutput;
const instances: CoreIndicatorInstance[] = [
  { id: 'macd', period: 9, fastPeriod: 12, slowPeriod: 26, signalPeriod: 9, enabled: true },
  { id: 'rsi', period: 14, enabled: false },
  { id: 'vwap', period: 1, enabled: true },
  { id: 'tv-correlation-coefficient-cc', period: 20, enabled: true, compareSymbol: 'equity:NASDAQ:QQQ' } as unknown as CoreIndicatorInstance,
];
const outputs = [line('macd:12:26:line', 'MACD'), line('macd:12:26:signal', 'Signal'), line('vwap:dataset', 'Anchored VWAP'), line('tv-correlation-coefficient-cc:value', 'CC')];

describe('alerts on chart indicators (TVP-1.3)', () => {
  it('offers the chart indicators with their lines, greying out what the server cannot evaluate', () => {
    const choices = alertIndicatorChoices(instances, outputs, new Set(['macd', 'tv-correlation-coefficient-cc']));
    expect(choices.map((choice) => [choice.key, choice.outputs.map((output) => output.key), choice.unavailable ?? null])).toEqual([
      ['macd', ['macd:12:26:line', 'macd:12:26:signal'], null],
      ['vwap', ['vwap:dataset'], 'Server alerts are not available for this indicator yet'],
      ['tv-correlation-coefficient-cc', ['tv-correlation-coefficient-cc:value'], 'Its extra inputs are not evaluated by server alerts yet'],
    ]);
    expect(choices[0].inputs).toMatchObject({ period: 9, fast_period: 12, slow_period: 26, signal_period: 9 });
    expect(defaultIndicatorSelection(choices)).toEqual({ key: 'macd', output: 'macd:12:26:line', operator: 'crossing' });
  });

  it('creates a conditions alert on the chosen line', () => {
    const choices = alertIndicatorChoices(instances, outputs, new Set(['macd']));
    const input = chartAlertCreateInput({ alertId: 'a', instrumentId: 'btc', bindingId: null, interval: '1h', threshold: 0, latestPrice: 1, expiration: 'never' });
    expect(withChartIndicatorCondition(input, choices, { key: 'macd', output: 'macd:12:26:signal', operator: 'crossing_up' }, '0.5')).toBe(true);
    expect(input.condition_type).toBe('conditions');
    expect(input.conditions).toEqual([{
      source: { kind: 'indicator', indicator_id: 'macd', inputs: expect.objectContaining({ period: 9, fast_period: 12 }), output: 'macd:12:26:signal' },
      operator: 'crossing_up',
      target: { kind: 'value', value: '0.5' },
    }]);
    // A greyed-out or unknown choice changes nothing.
    const other = chartAlertCreateInput({ alertId: 'b', instrumentId: 'btc', bindingId: null, interval: '1h', threshold: 0, latestPrice: 1, expiration: 'never' });
    expect(withChartIndicatorCondition(other, choices, { key: 'vwap', output: 'vwap:dataset', operator: 'crossing' }, '1')).toBe(false);
    expect(other.conditions).toBeUndefined();
  });

  it('picks the indicator, line and comparison', () => {
    const choices = alertIndicatorChoices(instances, outputs, new Set(['macd']));
    const onChange = vi.fn();
    render(<AlertIndicatorPicker choices={choices} selection={defaultIndicatorSelection(choices)} onChange={onChange} />);
    expect((screen.getByRole('option', { name: /VWAP.*not available/ }) as HTMLOptionElement).disabled).toBe(true);
    fireEvent.change(screen.getByLabelText('Alert indicator line'), { target: { value: 'macd:12:26:signal' } });
    expect(onChange).toHaveBeenLastCalledWith({ key: 'macd', output: 'macd:12:26:signal', operator: 'crossing' });
    fireEvent.change(screen.getByLabelText('Alert indicator comparison'), { target: { value: 'less_than' } });
    expect(onChange).toHaveBeenLastCalledWith({ key: 'macd', output: 'macd:12:26:line', operator: 'less_than' });
  });
});
