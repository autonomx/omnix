import { type ChartAlertPlacement } from './drawings/TradingDrawingOverlay';
import { type CoreIndicatorId } from './indicators/coreIndicators';
import { TradingChartPanelProps, isAlertIndicatorId } from './tradingChartPanelModel';
import type { useChartPanelState } from './useTradingChartPanelState';
import type { useChartView } from './useTradingChartPanelView';

/** What the context menu reads from the rest of the panel: the chart, its indicators and drawings, and the menu state. */
export type ChartContextMenuInput = Pick<TradingChartPanelProps, 'active' | 'indicators' | 'onActivate'
  | 'onClearIndicators' | 'onToggleIndicator'>
  & Pick<ReturnType<typeof useChartPanelState>, 'adapterRef' | 'contextMenu' | 'drawings' | 'hostRef'
    | 'setAlertPlacement' | 'setContextMenu' | 'setSelectedIndicator'>
  & Pick<ReturnType<typeof useChartView>, 'paneIndicators'>;

/** The chart's context menu: opening it at a point or pane, and its price, alert and template actions. Returns one `contextMenuActions` slice. */
export function useChartContextMenu(input: ChartContextMenuInput) {
  const {
    active, adapterRef, contextMenu, drawings, hostRef, indicators, onActivate, onClearIndicators, onToggleIndicator,
    paneIndicators, setAlertPlacement, setContextMenu, setSelectedIndicator,
  } = input;

  const openContextMenu = (point: ChartAlertPlacement, indicatorId?: CoreIndicatorId) => {
    if (!active) onActivate();
    setSelectedIndicator(null);
    const resolvedIndicatorId = indicatorId;
    const resolvedIndicator = resolvedIndicatorId
      ? indicators.find((indicator) => indicator.id === resolvedIndicatorId && indicator.enabled)
      : undefined;
    const alertIndicatorId = resolvedIndicatorId && isAlertIndicatorId(resolvedIndicatorId)
      ? resolvedIndicatorId
      : undefined;
    const stage = hostRef.current?.parentElement;
    const width = stage?.clientWidth ?? 0;
    const height = stage?.clientHeight ?? 0;
    setContextMenu({
      ...point,
      contextIndicatorId: resolvedIndicatorId,
      indicatorId: alertIndicatorId,
      chartIndicatorId: resolvedIndicatorId,
      indicatorPeriod: resolvedIndicator?.period,
      x: Math.max(6, Math.min(point.x, Math.max(6, width - 286))),
      y: Math.max(6, Math.min(point.y, Math.max(6, height - 420))),
    });
  };

  const handleStageContextMenu = (event: React.MouseEvent<HTMLDivElement>) => {
    event.preventDefault();
    const target = event.target as Element;
    if (target.closest('.trading-chart-context-menu, .trading-price-scale-menu, .trading-price-scale-trigger, .trading-chart-alert-editor, .trading-chart-table-view, .trading-chart-object-tree, .trading-chart-settings, .trading-indicator-pane-controls, .trading-indicator-object-toolbar')) return;
    const stage = event.currentTarget;
    const bounds = stage.getBoundingClientRect();
    const x = event.clientX - bounds.left;
    const y = event.clientY - bounds.top;
    const indicatorId = adapterRef.current?.indicatorPaneIdAtClientY(event.clientY);
    const indicator = indicatorId === null || indicatorId === undefined
      ? undefined
      : paneIndicators.find((item) => item.id === indicatorId);
    if (indicator) {
      const point = adapterRef.current?.drawingPointFromCoordinate(x, y);
      const indicatorValue = adapterRef.current?.indicatorValueFromClientY(indicator.id, event.clientY);
      if (point) openContextMenu({ ...point, price: indicatorValue ?? point.price, x, y, source: 'context-menu' }, indicator.id);
      return;
    }
    const point = adapterRef.current?.drawingPointFromCoordinate(x, y);
    if (point) openContextMenu({ ...point, x, y, source: 'context-menu' });
  };

  const copyContextPrice = () => {
    if (!contextMenu) return;
    void navigator.clipboard?.writeText(String(contextMenu.price));
  };

  const pasteContextPrice = () => {
    if (!contextMenu) return;
    void navigator.clipboard?.readText().then((value) => {
      const pasted = Number(value.trim());
      if (Number.isFinite(pasted)) setAlertPlacement({ ...contextMenu, price: pasted, source: 'context-menu' });
    }).catch(() => undefined);
  };

  const applyChartTemplate = (template: 'default' | 'clean' | 'momentum') => {
    if (template === 'clean') {
      onClearIndicators();
      drawings.removeAll();
      return;
    }
    if (template === 'momentum') {
      for (const id of ['rsi', 'macd'] as CoreIndicatorId[]) {
        if (!indicators.some((indicator) => indicator.id === id && indicator.enabled)) onToggleIndicator(id);
      }
    }
  };

  const contextMenuAlert = () => {
    // Any pane's indicator can be alerted on from the dialog's chart indicators (TVP-1.3).
    if (contextMenu) setAlertPlacement(contextMenu);
  };

  return {
    contextMenuActions: {
      open: openContextMenu, handleStageContextMenu, copyPrice: copyContextPrice, pastePrice: pasteContextPrice,
      applyTemplate: applyChartTemplate, addAlert: contextMenuAlert,
    },
  };
}
