import { beforeEach, describe, expect, it } from 'vitest';
import { useTradingStore } from './tradingStore';

beforeEach(() => {
  useTradingStore.setState({
    layout: 'one',
    activeChartId: 'chart-1',
    charts: [
      { chartId: 'chart-1', instrumentId: 'btc', interval: '1m', chartType: 'candlestick' },
      { chartId: 'chart-2', instrumentId: 'eth', interval: '5m', chartType: 'candlestick' },
      { chartId: 'chart-3', instrumentId: 'sol', interval: '15m', chartType: 'candlestick' },
      { chartId: 'chart-4', instrumentId: 'btc', interval: '1h', chartType: 'line' },
    ],
    links: { instrument: false, interval: false, crosshair: true, visibleRange: true },
  });
});

describe('Trading multi-chart store', () => {
  it('keeps active chart explicit across layout changes', () => {
    useTradingStore.getState().setActiveChart('chart-3');
    useTradingStore.getState().setLayout('four');
    expect(useTradingStore.getState().activeChartId).toBe('chart-3');
    expect(useTradingStore.getState().layout).toBe('four');
  });

  it('updates only one instrument while linking is disabled', () => {
    useTradingStore.getState().updateChart('chart-1', { instrumentId: 'sol' });
    expect(useTradingStore.getState().charts.map((chart) => chart.instrumentId)).toEqual(['sol', 'eth', 'sol', 'btc']);
  });

  it('propagates linked instrument and interval independently', () => {
    useTradingStore.getState().setLink('instrument', true);
    useTradingStore.getState().updateChart('chart-2', { instrumentId: 'btc' });
    expect(useTradingStore.getState().charts.every((chart) => chart.instrumentId === 'btc')).toBe(true);
    expect(useTradingStore.getState().charts.map((chart) => chart.interval)).toEqual(['1m', '5m', '15m', '1h']);

    useTradingStore.getState().setLink('interval', true);
    useTradingStore.getState().updateChart('chart-4', { interval: '4h' });
    expect(useTradingStore.getState().charts.every((chart) => chart.interval === '4h')).toBe(true);
  });
});
