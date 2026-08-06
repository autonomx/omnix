import { describe, expect, it } from 'vitest';
import { buildTradingWorkspaceExport } from './tradingExport';

describe('Trading workspace export', () => {
  it('exports only portable canonical state', () => {
    const payload = buildTradingWorkspaceExport({
      layout: 'two-horizontal',
      activeChartId: 'chart-1',
      charts: [{
        chartId: 'chart-1',
        instrumentId: 'equity:NASDAQ:AAPL',
        bindingId: 'yahoo:historical_polling:equity:NASDAQ:AAPL',
        interval: '1d',
        chartType: 'area',
        indicators: [{ id: 'bollinger', period: 20, standardDeviations: 2, enabled: true }],
      }],
      links: { instrument: false, interval: true, crosshair: true, visibleRange: true },
    });
    const text = JSON.stringify(payload);
    expect(payload.schemaVersion).toBe(1);
    expect(payload.layout).toBe('two-horizontal');
    expect(payload.charts[0].chartType).toBe('area');
    expect(text).not.toContain('WebSocket');
    expect(text).not.toContain('setLayout');
  });
});
