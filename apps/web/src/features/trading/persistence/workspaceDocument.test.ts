import { describe, expect, it } from 'vitest';
import { parseTradingWorkspace, serializeTradingWorkspace } from './workspaceDocument';

const state = {
  layout: 'four' as const,
  activeChartId: 'chart-3',
  charts: [
    { chartId: 'chart-1', instrumentId: 'btc', interval: '1m', chartType: 'candlestick' as const },
    { chartId: 'chart-2', instrumentId: 'eth', interval: '5m', chartType: 'line' as const },
  ],
  links: { instrument: false, interval: true, crosshair: true, visibleRange: false },
};

describe('Trading workspace document', () => {
  it('round trips exact layout, charts, active chart, and links', () => {
    const serialized = serializeTradingWorkspace(state);
    expect(parseTradingWorkspace(serialized)).toEqual(serialized);
  });

  it('rejects unknown schema versions and malformed charts', () => {
    expect(parseTradingWorkspace({ schemaVersion: 2, layout: 'four', charts: [] })).toBeNull();
    expect(parseTradingWorkspace({
      schemaVersion: 1,
      layout: 'one',
      charts: [{ chartId: 42 }],
      links: state.links,
    })).toBeNull();
  });

  it('does not persist runtime functions or provider payloads', () => {
    const serialized = serializeTradingWorkspace(state);
    const text = JSON.stringify(serialized);
    expect(text).not.toContain('setLayout');
    expect(text).not.toContain('raw');
    expect(serialized.charts[0].instrumentId).toBe('btc');
  });
});
