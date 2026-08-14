import { describe, expect, it } from 'vitest';
import { parseTradingWorkspace, serializeTradingWorkspace } from './workspaceDocument';

const state = {
  name: 'Research desk',
  layout: 'auto' as const,
  activeChartId: 'chart-2',
  charts: [
    { chartId: 'chart-1', instrumentId: 'btc', interval: '2h', chartType: 'candlestick' as const },
    { chartId: 'chart-2', instrumentId: 'eth', interval: '1w', chartType: 'line' as const },
    { chartId: 'chart-3', instrumentId: 'sol', interval: '4h', chartType: 'area' as const },
  ],
  links: { instrument: false, interval: true, crosshair: true, visibleRange: false },
  panels: { right: false, bottom: true },
  favoriteInstrumentIds: ['eth', 'btc', 'eth'],
};

describe('Trading workspace document', () => {
  it('round trips exact charts, panels, favorites, active chart, and links', () => {
    const serialized = serializeTradingWorkspace(state);
    expect(serialized.schemaVersion).toBe(2);
    expect(serialized.panels).toEqual({ right: false, bottom: true });
    expect(serialized.favoriteInstrumentIds).toEqual(['eth', 'btc']);
    expect(parseTradingWorkspace(serialized)).toEqual(serialized);
  });

  it('migrates fixed version-one layouts without exposing hidden charts', () => {
    const migrated = parseTradingWorkspace({
      schemaVersion: 1,
      layout: 'one',
      activeChartId: 'chart-3',
      charts: [
        { chartId: 'chart-1', instrumentId: 'btc', bindingId: null, interval: '1m', chartType: 'candlestick', indicators: [] },
        { chartId: 'chart-2', instrumentId: 'eth', bindingId: null, interval: '5m', chartType: 'candlestick', indicators: [] },
        { chartId: 'chart-3', instrumentId: 'sol', bindingId: null, interval: '15m', chartType: 'candlestick', indicators: [] },
        { chartId: 'chart-4', instrumentId: 'spy', bindingId: null, interval: '1d', chartType: 'line', indicators: [] },
      ],
      links: state.links,
      panels: { right: false },
      favoriteInstrumentIds: ['sol'],
    });
    expect(migrated?.schemaVersion).toBe(2);
    expect(migrated?.layout).toBe('columns-1');
    expect(migrated?.charts.map((chart) => chart.chartId)).toEqual(['chart-3']);
    expect(migrated?.activeChartId).toBe('chart-3');
    expect(migrated?.panels).toEqual({ right: false, bottom: true });
    expect(migrated?.favoriteInstrumentIds).toEqual(['sol']);
  });

  it('migrates saved Coinbase spot charts and favorites to Binance', () => {
    const migrated = parseTradingWorkspace({
      schemaVersion: 2,
      name: 'Main Workspace',
      layout: 'auto',
      activeChartId: 'chart-1',
      charts: [{
        chartId: 'chart-1',
        instrumentId: 'crypto:COINBASE:spot:BTC-USD',
        bindingId: 'coinbase:rest:crypto:COINBASE:spot:BTC-USD',
        interval: '1d',
        chartType: 'candlestick',
        indicators: [],
      }],
      links: state.links,
      panels: state.panels,
      favoriteInstrumentIds: ['crypto:COINBASE:spot:BTC-USD'],
    });

    expect(migrated?.charts[0]).toMatchObject({
      instrumentId: 'crypto:BINANCE:spot:BTC-USDT',
      bindingId: null,
    });
    expect(migrated?.favoriteInstrumentIds).toEqual(['crypto:BINANCE:spot:BTC-USDT']);
  });

  it('rejects unknown schema versions, layouts, and malformed charts', () => {
    expect(parseTradingWorkspace({ schemaVersion: 3, layout: 'auto', charts: [], links: state.links })).toBeNull();
    expect(parseTradingWorkspace({ schemaVersion: 2, layout: 'four', charts: state.charts, links: state.links })).toBeNull();
    expect(parseTradingWorkspace({
      schemaVersion: 2,
      layout: 'auto',
      charts: [{ chartId: 42 }],
      links: state.links,
    })).toBeNull();
  });

  it('does not persist runtime functions or provider payloads', () => {
    const serialized = serializeTradingWorkspace(state);
    const text = JSON.stringify(serialized);
    expect(text).not.toContain('setLayout');
    expect(text).not.toContain('rawProviderPayload');
    expect(serialized.charts[0].instrumentId).toBe('btc');
  });
});
