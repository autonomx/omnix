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
