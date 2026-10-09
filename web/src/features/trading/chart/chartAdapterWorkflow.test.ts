import { beforeEach, describe, expect, it, vi } from 'vitest';

type SeriesMock = ReturnType<typeof seriesMock>;

const series: SeriesMock[] = [];
let paneRects: Array<{ top: number; height: number }> = [];

function seriesMock() {
  return {
    setData: vi.fn(),
    update: vi.fn(),
    applyOptions: vi.fn(),
    priceScale: () => ({ applyOptions: vi.fn() }),
    createPriceLine: vi.fn((options: Record<string, unknown>) => ({ options })),
    removePriceLine: vi.fn(),
    lastValueData: vi.fn(() => ({ noData: false, price: 101, color: '#20c997' })),
    priceToCoordinate: vi.fn(() => 120),
  };
}

const chartMock = {
  applyOptions: vi.fn(),
  timeScale: () => ({ subscribeVisibleLogicalRangeChange: vi.fn(), unsubscribeVisibleLogicalRangeChange: vi.fn(), getVisibleLogicalRange: () => null }),
  addSeries: vi.fn(() => {
    const created = seriesMock();
    series.push(created);
    return created;
  }),
  priceScale: () => ({ width: () => 64 }),
  panes: () => paneRects.map((rect) => ({
    getHeight: () => rect.height,
    getHTMLElement: () => ({ getBoundingClientRect: () => ({ top: rect.top, height: rect.height }) }),
  })),
  remove: vi.fn(),
};

vi.mock('lightweight-charts', async (importOriginal) => ({
  ...(await importOriginal<typeof import('lightweight-charts')>()),
  createChart: vi.fn(() => chartMock),
}));

const { TradingChartAdapter } = await import('./chartAdapter');

describe('chart adapter workflow hooks (TVP-2.5)', () => {
  beforeEach(() => {
    series.length = 0;
    paneRects = [{ top: 0, height: 400 }, { top: 400, height: 120 }];
  });

  it('places the countdown under the last-price label and hides it off the pane', () => {
    const adapter = new TradingChartAdapter(document.createElement('div'));
    expect(adapter.lastPriceLabelPosition()).toEqual({ y: 120, color: '#20c997', side: 'right', scaleWidth: 64, paneHeight: 400 });
    series[0].priceToCoordinate.mockReturnValue(450);
    expect(adapter.lastPriceLabelPosition()).toBeNull();
    series[0].lastValueData.mockReturnValue({ noData: true } as never);
    expect(adapter.lastPriceLabelPosition()).toBeNull();
    adapter.setLatestValueLabelVisible(false);
    series[0].lastValueData.mockReturnValue({ noData: false, price: 1, color: '#fff' });
    series[0].priceToCoordinate.mockReturnValue(10);
    expect(adapter.lastPriceLabelPosition()).toBeNull();
  });

  it('draws, keeps and removes the pre/post-market price line', () => {
    const adapter = new TradingChartAdapter(document.createElement('div'));
    const price = series[0];
    adapter.setSessionPriceLine({ price: 187.5, title: 'Post-market', color: '#ff9f43' });
    expect(price.createPriceLine).toHaveBeenCalledTimes(1);
    expect(price.createPriceLine.mock.calls[0][0]).toMatchObject({ price: 187.5, title: 'Post-market', axisLabelVisible: true });
    adapter.setSessionPriceLine({ price: 187.5, title: 'Post-market', color: '#ff9f43' });
    expect(price.createPriceLine).toHaveBeenCalledTimes(1);
    adapter.setSessionPriceLine({ price: 188, title: 'Post-market', color: '#ff9f43' });
    expect(price.removePriceLine).toHaveBeenCalledTimes(1);
    expect(price.createPriceLine).toHaveBeenCalledTimes(2);
    adapter.setSessionPriceLine(null);
    expect(price.removePriceLine).toHaveBeenCalledTimes(2);
  });

  it('keeps indicator bar colours on live updates, for candles and bars (TVP-6.2)', () => {
    const adapter = new TradingChartAdapter(document.createElement('div'));
    const bar = {
      instrument_id: 'fixture', interval: '1m', start_time: '2026-08-05T12:00:00+00:00', end_time: '2026-08-05T12:01:00+00:00',
      open: '10', high: '12', low: '9', close: '11', volume: '5', is_final: false, adjustment_mode: 'raw', session: '24x7',
      provider: 'fixture', ingestion_revision: 1, received_at: '2026-08-05T12:01:00+00:00',
    } as never;
    (adapter as unknown as { barColors: Map<number, string> }).barColors = new Map([[Date.parse('2026-08-05T12:00:00Z') / 1000, '#26a69a']]);
    adapter.updateBar(bar);
    expect(series[0].update.mock.calls.at(-1)?.[0]).toMatchObject({ color: '#26a69a', wickColor: '#26a69a', borderColor: '#26a69a' });
    // The Bars chart type takes the bar-series branch on the same series.
    (adapter as unknown as { chartType: string }).chartType = 'bar';
    series[0].update.mockClear();
    adapter.updateBar({ ...(bar as object), ingestion_revision: 2 } as never);
    expect(series[0].update.mock.calls.at(-1)?.[0]).toMatchObject({ color: '#26a69a' });
  });

  it('tells which pane a double-click landed on', () => {
    const adapter = new TradingChartAdapter(document.createElement('div'));
    (adapter as unknown as { indicatorPaneIds: string[] }).indicatorPaneIds = ['rsi'];
    expect(adapter.paneAtClientY(100)).toEqual({ kind: 'main' });
    expect(adapter.paneAtClientY(450)).toEqual({ kind: 'indicator', id: 'rsi' });
    expect(adapter.paneAtClientY(600)).toBeNull();
  });
});
