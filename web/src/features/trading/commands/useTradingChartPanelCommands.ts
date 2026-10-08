import { PriceScaleMode } from 'lightweight-charts';
import { downloadUrl } from '../../../shared/download';
import type { TradingChartAdapter } from '../chart/chartAdapter';
import type { TradingPriceScaleMenuState, TradingPriceScaleMode } from '../TradingPriceScaleMenu';
import type { TradingChartPanelModel } from '../useTradingChartPanel';
import { useTradingCommand } from './useTradingCommands';

/** Bars that Ctrl+←/→ move: a quarter of the visible bars, at least 5. */
export function furtherStep(adapter: TradingChartAdapter): number {
  const range = adapter.api().timeScale().getVisibleLogicalRange();
  return range ? Math.max(5, Math.round((range.to - range.from) / 4)) : 5;
}

/** Moves the visible bars by `bars` (negative is left, toward older bars). */
export function moveChartBars(adapter: TradingChartAdapter, bars: number): void {
  const timeScale = adapter.api().timeScale();
  const range = timeScale.getVisibleLogicalRange();
  if (!range) return;
  timeScale.setVisibleLogicalRange({ from: range.from + bars, to: range.to + bars });
}

/** Zooms around the latest visible bar, as TradingView's Ctrl+↑/↓ do. */
export function zoomChart(adapter: TradingChartAdapter, direction: 'in' | 'out'): void {
  const width = adapter.api().timeScale().width();
  adapter.zoomAtCoordinate(Math.max(0, width - 1), direction === 'in' ? -100 : 100);
}

const MODE_VALUES: Record<TradingPriceScaleMode, PriceScaleMode> = {
  normal: PriceScaleMode.Normal,
  percentage: PriceScaleMode.Percentage,
  indexed: PriceScaleMode.IndexedTo100,
  logarithmic: PriceScaleMode.Logarithmic,
};

type ChartCommandModel = Pick<
  TradingChartPanelModel,
  | 'active' | 'adapter' | 'chartId' | 'priceScaleSettings' | 'setPriceScaleSettings' | 'selectedRangeRef' | 'setSelectedRangeLabel'
  | 'openGoToDate' | 'replayMode'
>;

/** The active chart's keyboard commands (TVP-2.1): move, zoom, reset, price scale, snapshot and go to date (TVP-2.5). */
export function useTradingChartPanelCommands(ws: ChartCommandModel): void {
  const {
    active, adapter, chartId, openGoToDate, priceScaleSettings, replayMode, setPriceScaleSettings, selectedRangeRef, setSelectedRangeLabel,
  } = ws;
  const ready = () => active && adapter !== null;
  const withAdapter = (action: (target: TradingChartAdapter) => void) => () => {
    if (adapter) action(adapter);
  };
  const updateScale = (patch: Partial<TradingPriceScaleMenuState>) => setPriceScaleSettings((current) => ({ ...current, ...patch }));
  const toggleMode = (mode: TradingPriceScaleMode) => withAdapter((target) => {
    const next = priceScaleSettings.mode === mode ? 'normal' : mode;
    target.setPriceScaleMode(MODE_VALUES[next]);
    updateScale({ mode: next });
  });

  useTradingCommand('chart.moveLeft', withAdapter((target) => moveChartBars(target, -1)), ready);
  useTradingCommand('chart.moveRight', withAdapter((target) => moveChartBars(target, 1)), ready);
  useTradingCommand('chart.moveFurtherLeft', withAdapter((target) => moveChartBars(target, -furtherStep(target))), ready);
  useTradingCommand('chart.moveFurtherRight', withAdapter((target) => moveChartBars(target, furtherStep(target))), ready);
  useTradingCommand('chart.zoomIn', withAdapter((target) => zoomChart(target, 'in')), ready);
  useTradingCommand('chart.zoomOut', withAdapter((target) => zoomChart(target, 'out')), ready);
  useTradingCommand('chart.reset', withAdapter((target) => {
    selectedRangeRef.current = undefined;
    setSelectedRangeLabel('All');
    target.fitContent();
    target.setPriceScaleAutoScale(true);
    updateScale({ autoScale: true });
  }), ready);
  useTradingCommand('chart.invertScale', withAdapter((target) => {
    target.setPriceScaleInvert(!priceScaleSettings.invertScale);
    updateScale({ invertScale: !priceScaleSettings.invertScale });
  }), ready);
  useTradingCommand('chart.logScale', toggleMode('logarithmic'), ready);
  useTradingCommand('chart.percentScale', toggleMode('percentage'), ready);
  useTradingCommand('chart.snapshot', withAdapter((target) => downloadUrl(target.snapshotDataUrl(), `${chartId}.png`)), ready);
  // Like the toolbar button, go to date is off during replay.
  useTradingCommand('chart.goToDate', openGoToDate, () => ready() && !replayMode);
}
