import { beforeEach, describe, expect, it } from 'vitest';
import {
  MAX_TRADING_CHARTS,
  defaultTradingIndicators,
  useTradingStore,
  type TradingChartState,
} from './tradingStore';

function chart(chartId: string, instrumentId: string, interval: string): TradingChartState {
  return {
    chartId,
    instrumentId,
    bindingId: null,
    interval,
    chartType: 'candlestick',
    indicators: defaultTradingIndicators(),
  };
}

beforeEach(() => {
  useTradingStore.setState({
    layout: 'auto',
    activeChartId: 'chart-1',
    charts: [
      chart('chart-1', 'btc', '1m'),
      chart('chart-2', 'eth', '5m'),
      chart('chart-3', 'sol', '15m'),
      chart('chart-4', 'btc', '1h'),
    ],
    links: { instrument: false, interval: false, crosshair: true, visibleRange: true },
    panels: { right: true, bottom: true },
    favoriteInstrumentIds: [],
  });
});

describe('Trading multi-chart store', () => {
  it('keeps active chart explicit across grid changes', () => {
    useTradingStore.getState().setActiveChart('chart-3');
    useTradingStore.getState().setLayout('columns-3');
    expect(useTradingStore.getState().activeChartId).toBe('chart-3');
    expect(useTradingStore.getState().layout).toBe('columns-3');
  });

  it('supports one, two, three, four, and more charts', () => {
    useTradingStore.getState().setChartCount(3);
    expect(useTradingStore.getState().charts).toHaveLength(3);

    useTradingStore.getState().setChartCount(7);
    expect(useTradingStore.getState().charts).toHaveLength(7);
    expect(new Set(useTradingStore.getState().charts.map((item) => item.chartId)).size).toBe(7);

    useTradingStore.getState().setChartCount(MAX_TRADING_CHARTS + 20);
    expect(useTradingStore.getState().charts).toHaveLength(MAX_TRADING_CHARTS);
  });

  it('adds and removes the active chart without allowing an empty workspace', () => {
    useTradingStore.getState().setChartCount(1);
    useTradingStore.getState().addChart();
    const added = useTradingStore.getState().activeChartId;
    expect(useTradingStore.getState().charts).toHaveLength(2);

    useTradingStore.getState().removeChart(added);
    expect(useTradingStore.getState().charts).toHaveLength(1);
    expect(useTradingStore.getState().activeChartId).toBe('chart-1');

    useTradingStore.getState().removeChart('chart-1');
    expect(useTradingStore.getState().charts).toHaveLength(1);
  });

  it('updates only one instrument while linking is disabled', () => {
    useTradingStore.getState().updateChart('chart-1', { instrumentId: 'sol' });
    expect(useTradingStore.getState().charts.map((item) => item.instrumentId)).toEqual(['sol', 'eth', 'sol', 'btc']);
  });

  it('propagates linked instrument and interval independently', () => {
    useTradingStore.getState().setLink('instrument', true);
    useTradingStore.getState().updateChart('chart-2', { instrumentId: 'btc' });
    expect(useTradingStore.getState().charts.every((item) => item.instrumentId === 'btc')).toBe(true);
    expect(useTradingStore.getState().charts.map((item) => item.interval)).toEqual(['1m', '5m', '15m', '1h']);

    useTradingStore.getState().setLink('interval', true);
    useTradingStore.getState().updateChart('chart-4', { interval: '2h' });
    expect(useTradingStore.getState().charts.every((item) => item.interval === '2h')).toBe(true);
  });

  it('stores panel visibility and canonical instrument favorites', () => {
    useTradingStore.getState().setPanel('right', false);
    useTradingStore.getState().toggleFavoriteInstrument('equity:NASDAQ:AAPL');
    expect(useTradingStore.getState().panels).toEqual({ right: false, bottom: true });
    expect(useTradingStore.getState().favoriteInstrumentIds).toEqual(['equity:NASDAQ:AAPL']);
    useTradingStore.getState().toggleFavoriteInstrument('equity:NASDAQ:AAPL');
    expect(useTradingStore.getState().favoriteInstrumentIds).toEqual([]);
  });

  it('reorders enabled secondary indicators without moving overlays', () => {
    const indicators = defaultTradingIndicators().map((indicator) => (
      indicator.id === 'macd' || indicator.id === 'atr' ? { ...indicator, enabled: true } : indicator
    ));
    useTradingStore.getState().setIndicators('chart-1', indicators);

    useTradingStore.getState().moveIndicator('chart-1', 'rsi', 'down');

    expect(useTradingStore.getState().charts[0].indicators.map((item) => item.id)).toEqual([
      'sma', 'ema', 'macd', 'rsi', 'bollinger', 'atr', 'vwap',
    ]);
    expect(useTradingStore.getState().charts[0].indicators.find((item) => item.id === 'sma')?.enabled).toBe(true);
  });

  it('keeps secondary indicator order bounded at the first and last pane', () => {
    const indicators = defaultTradingIndicators().map((indicator) => (
      indicator.id === 'macd' ? { ...indicator, enabled: true } : indicator
    ));
    useTradingStore.getState().setIndicators('chart-1', indicators);
    const before = useTradingStore.getState().charts[0].indicators.map((item) => item.id);

    useTradingStore.getState().moveIndicator('chart-1', 'rsi', 'up');
    expect(useTradingStore.getState().charts[0].indicators.map((item) => item.id)).toEqual(before);

    useTradingStore.getState().moveIndicator('chart-1', 'macd', 'down');
    expect(useTradingStore.getState().charts[0].indicators.map((item) => item.id)).toEqual(before);
  });
});
