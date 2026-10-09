import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { ChartLinkGroupButton } from './ChartLinkGroupButton';
import { parseTradingWorkspace, serializeTradingWorkspace } from './persistence/workspaceDocument';
import { defaultTradingIndicators, useTradingStore, type TradingChartState, type TradingTabState } from './tradingStore';

function chart(chartId: string, instrumentId: string, linkGroup?: TradingChartState['linkGroup']): TradingChartState {
  return { chartId, instrumentId, bindingId: 'feed', interval: '1h', chartType: 'candlestick', indicators: defaultTradingIndicators(), ...(linkGroup ? { linkGroup } : {}) };
}

const links = { instrument: false, interval: false, crosshair: true, visibleRange: false };
const panels = { right: true, bottom: true };
const tab = (tabId: string, charts: TradingChartState[]): TradingTabState => ({ tabId, name: tabId, layout: 'auto', activeChartId: charts[0].chartId, charts, links, panels });

beforeEach(() => {
  const active = [chart('a1', 'btc', 'red'), chart('a2', 'eth', 'red'), chart('a3', 'sol'), chart('a4', 'ada', 'blue')];
  useTradingStore.setState({
    activeTabId: 'tab-1',
    tabs: [tab('tab-1', active), tab('tab-2', [chart('b1', 'xrp', 'red'), chart('b2', 'dot', 'blue')])],
    charts: active,
    activeChartId: 'a1',
    links,
    panels,
  });
});
afterEach(cleanup);

const symbols = () => {
  const state = useTradingStore.getState();
  return {
    active: Object.fromEntries(state.charts.map((item) => [item.chartId, item.instrumentId])),
    other: Object.fromEntries(state.tabs.find((item) => item.tabId === 'tab-2')!.charts.map((item) => [item.chartId, item.instrumentId])),
  };
};

describe('colour link groups (TVP-4.1)', () => {
  it('carries a symbol change to the group only, in every tab', () => {
    act(() => useTradingStore.getState().updateChart('a1', { instrumentId: 'doge' }));
    expect(symbols()).toEqual({ active: { a1: 'doge', a2: 'doge', a3: 'sol', a4: 'ada' }, other: { b1: 'doge', b2: 'dot' } });
    // Members resolve their own binding again.
    expect(useTradingStore.getState().charts.find((item) => item.chartId === 'a2')?.bindingId).toBeNull();
    // A chart outside any group changes alone.
    act(() => useTradingStore.getState().updateChart('a3', { instrumentId: 'avax' }));
    expect(symbols().active).toEqual({ a1: 'doge', a2: 'doge', a3: 'avax', a4: 'ada' });
    // An interval change is not a symbol change.
    act(() => useTradingStore.getState().updateChart('a1', { interval: '5m' }));
    expect(useTradingStore.getState().charts.find((item) => item.chartId === 'a2')?.interval).toBe('1h');
  });

  it('joins a group with its symbol, and leaves it', () => {
    act(() => useTradingStore.getState().setChartLinkGroup('a3', 'blue'));
    expect(symbols().active.a3).toBe('ada');
    act(() => useTradingStore.getState().setChartLinkGroup('a3', null));
    expect(useTradingStore.getState().charts.find((item) => item.chartId === 'a3')?.linkGroup).toBeUndefined();
    // The first chart in a group keeps its own symbol.
    act(() => useTradingStore.getState().setChartLinkGroup('a3', 'green'));
    expect(symbols().active.a3).toBe('ada');
  });

  it('is saved with the chart; an unknown colour is dropped', () => {
    const document = serializeTradingWorkspace({ name: 'Desk', layout: 'auto', activeChartId: 'a1', charts: [chart('a1', 'btc', 'red'), chart('a2', 'eth')], links, panels, favoriteInstrumentIds: [] });
    expect(parseTradingWorkspace(document)?.charts?.[0].linkGroup).toBe('red');
    const unknown = { ...document, charts: [{ ...document.charts[0], linkGroup: 'magenta' }, document.charts[1]] };
    expect(parseTradingWorkspace(unknown)?.charts?.[0].linkGroup).toBeUndefined();
  });

  it('picks the group from the chart header', () => {
    render(<ChartLinkGroupButton chartId="a3" group={undefined} />);
    fireEvent.click(screen.getByRole('button', { name: 'No link group: change' }));
    fireEvent.click(screen.getByRole('menuitemradio', { name: 'Red' }));
    expect(useTradingStore.getState().charts.find((item) => item.chartId === 'a3')).toMatchObject({ linkGroup: 'red', instrumentId: 'btc' });
  });
});
