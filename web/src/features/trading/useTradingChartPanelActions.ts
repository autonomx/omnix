import { useEffect } from 'react';
import { DEFAULT_TRADING_RIGHT_OFFSET } from './chart/chartAdapter';
import { type CoreIndicatorId } from './indicators/coreIndicators';
import { isIntervalAvailable } from './tradingIntervals';
import { TradingChartPanelProps, applyVisibleRange, closestSupportedInterval, rightOffsetOptions, rightOffsetStorageKey } from './tradingChartPanelModel';
import type { useChartPanelState } from './useTradingChartPanelState';
import type { useChartIndicatorScheduling } from './useTradingChartPanelData';
import type { useChartPanelData } from './useTradingChartPanelData';
import type { useChartLifecycle } from './useTradingChartPanelLifecycle';
import type { useChartSync } from './useTradingChartPanelSync';
import type { useChartView } from './useTradingChartPanelView';

/** What the pane actions read from the rest of the panel: the chart, the pane state and the focus callback. */
export type ChartIndicatorPaneInput = Pick<TradingChartPanelProps, 'chartFocusMode' | 'onChartFocusChange' | 'onToggleIndicator'>
  & Pick<ReturnType<typeof useChartPanelState>, 'adapterRef' | 'fullscreenIndicatorRef' | 'fullscreenMainPaneRef'
    | 'indicatorResizeRef' | 'minimizedIndicatorsRef' | 'setFullscreenIndicator' | 'setFullscreenMainPane'
    | 'setHoveredIndicatorPane' | 'setMinimizedIndicators' | 'setResizingIndicatorPane' | 'setSettingsIndicator'>
  & Pick<ReturnType<typeof useChartIndicatorScheduling>, 'refreshIndicatorPanes'>;

/** Indicator pane actions: fullscreen, minimize, close and resize. Returns one `panes` slice. */
export function useChartIndicatorActions(input: ChartIndicatorPaneInput) {
  const {
    adapterRef, chartFocusMode, fullscreenIndicatorRef, fullscreenMainPaneRef, indicatorResizeRef,
    minimizedIndicatorsRef, onChartFocusChange, onToggleIndicator, refreshIndicatorPanes, setFullscreenIndicator,
    setFullscreenMainPane, setHoveredIndicatorPane, setMinimizedIndicators, setResizingIndicatorPane,
    setSettingsIndicator,
  } = input;

  const toggleFullscreen = () => {
    const nextFocused = !chartFocusMode;
    fullscreenIndicatorRef.current = null;
    setFullscreenIndicator(null);
    adapterRef.current?.setIndicatorPaneFullscreen(null);
    fullscreenMainPaneRef.current = nextFocused;
    setFullscreenMainPane(nextFocused);
    if (nextFocused) adapterRef.current?.setMainPaneFullscreen(true);
    else adapterRef.current?.setMainPaneFullscreen(false);
    onChartFocusChange(nextFocused);
  };

  const toggleMinimizedIndicator = (id: CoreIndicatorId) => {
    if (fullscreenIndicatorRef.current === id) return;
    setMinimizedIndicators((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      minimizedIndicatorsRef.current = next;
      return next;
    });
  };

  const resetIndicatorPaneView = (id: CoreIndicatorId) => {
    // Resetting a price scale causes Lightweight Charts to reflow the pane.
    // Clear the hover latch at the same time so the controls remain hover-only
    // after that reflow.
    setHoveredIndicatorPane(null);
    adapterRef.current?.resetIndicatorPaneView(id);
  };

  const toggleFullscreenIndicator = (id: CoreIndicatorId) => {
    const next = fullscreenIndicatorRef.current === id ? null : id;
    fullscreenIndicatorRef.current = next;
    setFullscreenIndicator(next);
    if (next) {
      fullscreenMainPaneRef.current = false;
      setFullscreenMainPane(false);
      adapterRef.current?.setMainPaneFullscreen(false);
      setMinimizedIndicators((current) => {
        const updated = new Set(current);
        updated.delete(id);
        minimizedIndicatorsRef.current = updated;
        return updated;
      });
      adapterRef.current?.setIndicatorPaneFullscreen(next);
      onChartFocusChange(true);
      return;
    }
    fullscreenMainPaneRef.current = false;
    setFullscreenMainPane(false);
    adapterRef.current?.setIndicatorPaneFullscreen(null);
    onChartFocusChange(false);
  };

  const closeIndicator = (id: CoreIndicatorId) => {
    if (fullscreenIndicatorRef.current === id) {
      fullscreenIndicatorRef.current = null;
      setFullscreenIndicator(null);
      adapterRef.current?.setIndicatorPaneFullscreen(null);
      onChartFocusChange(false);
    }
    setSettingsIndicator((current) => current?.id === id ? null : current);
    setMinimizedIndicators((current) => {
      const next = new Set(current);
      next.delete(id);
      minimizedIndicatorsRef.current = next;
      return next;
    });
    onToggleIndicator(id);
  };

  const startIndicatorPaneResize = (event: React.PointerEvent<HTMLDivElement>, id: CoreIndicatorId, edge: 'top' | 'bottom') => {
    if (event.button !== 0 || event.pointerType === 'touch' || fullscreenIndicatorRef.current !== null) return;
    indicatorResizeRef.current = { id, edge, pointerId: event.pointerId, lastY: event.clientY, target: event.currentTarget };
    setResizingIndicatorPane(id);
    event.currentTarget.setPointerCapture(event.pointerId);
    event.preventDefault();
    event.stopPropagation();
  };

  useEffect(() => {
    const move = (event: PointerEvent) => {
      const resize = indicatorResizeRef.current;
      if (!resize || resize.pointerId !== event.pointerId) return;
      const deltaY = event.clientY - resize.lastY;
      resize.lastY = event.clientY;
      adapterRef.current?.resizeIndicatorPaneByPixels(resize.id, resize.edge, deltaY);
      refreshIndicatorPanes(adapterRef.current);
      event.preventDefault();
    };
    const finish = (event: PointerEvent) => {
      const resize = indicatorResizeRef.current;
      if (!resize || resize.pointerId !== event.pointerId) return;
      if (resize.target.hasPointerCapture(event.pointerId)) resize.target.releasePointerCapture(event.pointerId);
      indicatorResizeRef.current = null;
      setResizingIndicatorPane(null);
      event.preventDefault();
    };
    window.addEventListener('pointermove', move, { passive: false });
    window.addEventListener('pointerup', finish, { passive: false });
    window.addEventListener('pointercancel', finish, { passive: false });
    return () => {
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', finish);
      window.removeEventListener('pointercancel', finish);
    };
  }, [refreshIndicatorPanes, adapterRef, indicatorResizeRef, setResizingIndicatorPane]);

  return {
    panes: {
      toggleFullscreen, toggleMinimized: toggleMinimizedIndicator, resetView: resetIndicatorPaneView,
      toggleIndicatorFullscreen: toggleFullscreenIndicator, close: closeIndicator, startResize: startIndicatorPaneResize,
    },
  };
}

/** Visible-range and pointer actions. */
export function useChartRangeActions(ws: TradingChartPanelProps & ReturnType<typeof useChartPanelState> & ReturnType<typeof useChartIndicatorScheduling> & ReturnType<typeof useChartPanelData> & ReturnType<typeof useChartLifecycle> & ReturnType<typeof useChartSync> & ReturnType<typeof useChartView> & ReturnType<typeof useChartIndicatorActions>) {
  const {
    adapterRef, allBarsRef, barsRef, chartQuery, drawingTool, indicatorPaneGeometry, interval, onChangeInterval,
    pendingRangeIntervalRef, replayChoosingStart, rightOffset, selectedRangeRef, selectedTimezone,
    setHoveredIndicatorPane, setPriceScaleHovered, setReplaySelectionIndex, setRightOffset, setSelectedRangeLabel,
  } = ws;

  const changeRightOffset = (value: string | number) => {
    const parsed = Number(value);
    const next = rightOffsetOptions.includes(parsed as typeof rightOffsetOptions[number])
      ? parsed
      : DEFAULT_TRADING_RIGHT_OFFSET;
    setRightOffset(next);
    selectedRangeRef.current = null;
    setSelectedRangeLabel('All');
    adapterRef.current?.setRightOffset(next);
    adapterRef.current?.fitContent();
    try {
      window.localStorage.setItem(rightOffsetStorageKey, String(next));
    } catch {
      // The setting remains active for the current session when storage is unavailable.
    }
  };

  const showRange = (label: string, days: number | null, requestedInterval: string) => {
    selectedRangeRef.current = days;
    setSelectedRangeLabel(label);
    const supportedIntervals = chartQuery.data?.binding.supported_intervals ?? [];
    const nextInterval = isIntervalAvailable(requestedInterval, supportedIntervals)
      ? requestedInterval
      : closestSupportedInterval(requestedInterval, supportedIntervals);
    pendingRangeIntervalRef.current = interval === nextInterval ? null : nextInterval;
    onChangeInterval(nextInterval);
    const chart = adapterRef.current?.api();
    if (!chart) return;
    if (interval === nextInterval) applyVisibleRange(chart, days, barsRef.current, interval, rightOffset, selectedTimezone);
  };

  const handleStagePointerMove = (event: React.PointerEvent<HTMLDivElement>) => {
    const targetAdapter = adapterRef.current;
    const target = event.target as Element;
    // Drawing and alert tools own the chart pointer. Do not let transient pane
    // hover chrome appear underneath that interaction and intercept placement.
    if (drawingTool !== 'cursor') {
      setHoveredIndicatorPane(null);
    } else if (targetAdapter) {
      const bounds = event.currentTarget.getBoundingClientRect();
      const y = event.clientY - bounds.top;
      const hoveredPane = indicatorPaneGeometry.find((pane) => y >= pane.top && y <= pane.top + pane.height);
      const nextHoveredPane = hoveredPane ? hoveredPane.id as CoreIndicatorId : null;
      setHoveredIndicatorPane((current) => current === nextHoveredPane ? current : nextHoveredPane);
    } else {
      setHoveredIndicatorPane(null);
    }
    if (target.closest('.trading-y-axis-controls')) {
      setPriceScaleHovered(true);
      return;
    }
    if (!targetAdapter) {
      setPriceScaleHovered(false);
      return;
    }
    const bounds = event.currentTarget.getBoundingClientRect();
    if (replayChoosingStart && !target.closest('button, input, select, textarea, [role="dialog"]')) {
      const x = event.clientX - bounds.left;
      if (!targetAdapter.isPriceScaleCoordinate(x)) {
        const index = targetAdapter.barIndexAtCoordinate(x, allBarsRef.current.length);
        if (index !== null) setReplaySelectionIndex(index);
      }
    }
    const nextHovered = targetAdapter.isMainPriceScaleCoordinate(event.clientX - bounds.left);
    setPriceScaleHovered((current) => current === nextHovered ? current : nextHovered);
  };

  const handleStagePointerLeave = () => {
    setPriceScaleHovered(false);
    setHoveredIndicatorPane(null);
  };

  return { changeRightOffset, showRange, handleStagePointerMove, handleStagePointerLeave };
}
