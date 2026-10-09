// Colour link groups (TVP-4.1): a chart can join one colour group, or none.
// Charts in a group share their symbol across every tab; the tab-wide links
// ("link all") stay as they are. A change is applied in one store update, so
// it can't echo back and forth between charts.
import type { TradingChartState, TradingTabState } from './tradingStore';

export const CHART_LINK_GROUPS = ['red', 'orange', 'yellow', 'green', 'blue', 'purple'] as const;
export type ChartLinkGroup = typeof CHART_LINK_GROUPS[number];

export const CHART_LINK_GROUP_LABELS: Record<ChartLinkGroup, string> = {
  red: 'Red', orange: 'Orange', yellow: 'Yellow', green: 'Green', blue: 'Blue', purple: 'Purple',
};

export function isChartLinkGroup(value: unknown): value is ChartLinkGroup {
  return typeof value === 'string' && (CHART_LINK_GROUPS as readonly string[]).includes(value);
}

type Symbol = Pick<TradingChartState, 'instrumentId' | 'bindingId'>;

/** The charts with the group's symbol: members take it (the binding resolves again for each chart). */
export function withGroupSymbol(charts: readonly TradingChartState[], group: ChartLinkGroup, symbol: Symbol, except?: string): TradingChartState[] {
  return charts.map((chart) => (
    chart.linkGroup === group && chart.chartId !== except && chart.instrumentId !== symbol.instrumentId
      ? { ...chart, instrumentId: symbol.instrumentId, bindingId: null }
      : chart
  ));
}

/** Every other tab with the group's symbol applied to its members. */
export function tabsWithGroupSymbol(tabs: readonly TradingTabState[], activeTabId: string, group: ChartLinkGroup, symbol: Symbol): TradingTabState[] {
  return tabs.map((tab) => {
    if (tab.tabId === activeTabId) return tab;
    const charts = withGroupSymbol(tab.charts, group, symbol);
    return charts.some((chart, index) => chart !== tab.charts[index]) ? { ...tab, charts } : tab;
  });
}

/** The symbol a chart joining `group` takes: a member's in this tab, else in another tab; null when it is the first. */
export function groupSymbol(
  charts: readonly TradingChartState[],
  tabs: readonly TradingTabState[],
  activeTabId: string,
  group: ChartLinkGroup,
  except: string,
): Symbol | null {
  const member = charts.find((chart) => chart.linkGroup === group && chart.chartId !== except)
    ?? tabs.filter((tab) => tab.tabId !== activeTabId).flatMap((tab) => tab.charts).find((chart) => chart.linkGroup === group);
  return member ? { instrumentId: member.instrumentId, bindingId: member.bindingId } : null;
}

type LinkState = { charts: readonly TradingChartState[]; tabs: readonly TradingTabState[]; activeTabId: string };

/**
 * A symbol change on `chartId` carried to its group: the active tab's charts (after the change) and a function that
 * applies it to the other tabs. Null when the chart is in no group or the symbol did not change.
 */
export function linkedSymbolChange(
  state: LinkState,
  chartId: string,
  instrumentId: string | undefined,
  charts: readonly TradingChartState[],
): { charts: TradingChartState[]; otherTabs: (tabs: readonly TradingTabState[]) => TradingTabState[] } | null {
  const group = state.charts.find((chart) => chart.chartId === chartId)?.linkGroup;
  if (!group || instrumentId === undefined) return null;
  const symbol = { instrumentId, bindingId: null };
  return {
    charts: withGroupSymbol(charts, group, symbol, chartId),
    otherTabs: (tabs) => tabsWithGroupSymbol(tabs, state.activeTabId, group, symbol),
  };
}

/** The active tab's charts with `chartId` in `group` (taking the group's symbol), or out of any group with null. */
export function chartsJoiningGroup(state: LinkState, chartId: string, group: ChartLinkGroup | null): TradingChartState[] {
  const symbol = group ? groupSymbol(state.charts, state.tabs, state.activeTabId, group, chartId) : null;
  return state.charts.map((chart) => {
    if (chart.chartId !== chartId) return chart;
    const rest = { ...chart };
    delete rest.linkGroup;
    if (!group) return rest;
    return symbol && symbol.instrumentId !== chart.instrumentId
      ? { ...rest, linkGroup: group, instrumentId: symbol.instrumentId, bindingId: null }
      : { ...rest, linkGroup: group };
  });
}
