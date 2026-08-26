import { TradingChartAdapter } from './chartAdapter';

type NumericRange = { from: number; to: number };
type PriceScaleSnapshot = { autoScale: boolean; range: NumericRange | null };
type ViewportSnapshot = {
  logicalRange: NumericRange | null;
  left: PriceScaleSnapshot;
  right: PriceScaleSnapshot;
};

const viewports = new Map<string, ViewportSnapshot>();
const restoredAdapters = new WeakSet<TradingChartAdapter>();
let installed = false;

function finiteRange(value: NumericRange | null): NumericRange | null {
  if (!value || !Number.isFinite(value.from) || !Number.isFinite(value.to) || value.to <= value.from) return null;
  return { from: value.from, to: value.to };
}

function workspaceId(): string {
  if (typeof document === 'undefined') return 'workspace';
  const select = document.querySelector<HTMLSelectElement>('.trading-workspace-switcher select');
  return select?.value || 'workspace';
}

function viewportKey(adapter: TradingChartAdapter): string | null {
  if (typeof document === 'undefined') return null;
  const chartElement = adapter.api().chartElement();
  const panel = chartElement.closest<HTMLElement>('[data-chart-id]');
  const chartId = panel?.dataset.chartId;
  return chartId ? `${workspaceId()}:${chartId}` : null;
}

function priceScaleSnapshot(adapter: TradingChartAdapter, side: 'left' | 'right'): PriceScaleSnapshot {
  const scale = adapter.api().priceScale(side);
  return {
    autoScale: Boolean(scale.options().autoScale),
    range: finiteRange(scale.getVisibleRange()),
  };
}

function capture(adapter: TradingChartAdapter): void {
  const key = viewportKey(adapter);
  if (!key) return;
  const api = adapter.api();
  viewports.set(key, {
    logicalRange: finiteRange(api.timeScale().getVisibleLogicalRange()),
    left: priceScaleSnapshot(adapter, 'left'),
    right: priceScaleSnapshot(adapter, 'right'),
  });
}

function restorePriceScale(adapter: TradingChartAdapter, side: 'left' | 'right', snapshot: PriceScaleSnapshot): void {
  const scale = adapter.api().priceScale(side);
  if (snapshot.autoScale) {
    scale.setAutoScale(true);
    return;
  }
  if (!snapshot.range) return;
  scale.setAutoScale(false);
  scale.setVisibleRange(snapshot.range);
}

function restore(adapter: TradingChartAdapter): void {
  if (restoredAdapters.has(adapter)) return;
  restoredAdapters.add(adapter);
  const key = viewportKey(adapter);
  const snapshot = key ? viewports.get(key) : undefined;
  if (!snapshot) return;
  if (snapshot.logicalRange) adapter.api().timeScale().setVisibleLogicalRange(snapshot.logicalRange);
  restorePriceScale(adapter, 'left', snapshot.left);
  restorePriceScale(adapter, 'right', snapshot.right);
}

/**
 * Preserve manual time/price viewport state when React remounts chart panels
 * during trading-tab or workspace switches. The persistence key combines the
 * saved workspace id with the chart id, so two workspaces never share zoom.
 */
export function installTradingChartViewportPersistence(): void {
  if (installed) return;
  installed = true;

  const originalSetBars = TradingChartAdapter.prototype.setBars;
  TradingChartAdapter.prototype.setBars = function (...args: Parameters<TradingChartAdapter['setBars']>) {
    const result = originalSetBars.apply(this, args);
    restore(this);
    return result;
  };

  const originalDestroy = TradingChartAdapter.prototype.destroy;
  TradingChartAdapter.prototype.destroy = function (...args: Parameters<TradingChartAdapter['destroy']>) {
    capture(this);
    return originalDestroy.apply(this, args);
  };
}
