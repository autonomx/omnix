import { useEffect } from 'react';
import { TradingChartPanelProps } from './tradingChartPanelModel';
import type { useChartPanelState } from './useTradingChartPanelState';
import type { useChartIndicatorScheduling } from './useTradingChartPanelData';
import type { useChartPanelData } from './useTradingChartPanelData';
import type { useChartLifecycle } from './useTradingChartPanelLifecycle';
import type { useChartSync } from './useTradingChartPanelSync';
import type { useChartView } from './useTradingChartPanelView';
import type { useChartIndicatorActions } from './useTradingChartPanelActions';
import type { useChartRangeActions } from './useTradingChartPanelActions';

/** Bar replay: choosing the start, stepping, and leaving replay. */
export function useChartReplayActions(ws: TradingChartPanelProps & ReturnType<typeof useChartPanelState> & ReturnType<typeof useChartIndicatorScheduling> & ReturnType<typeof useChartPanelData> & ReturnType<typeof useChartLifecycle> & ReturnType<typeof useChartSync> & ReturnType<typeof useChartView> & ReturnType<typeof useChartIndicatorActions> & ReturnType<typeof useChartRangeActions>) {
  const {
    active, adapter, adapterRef, allBarsRef, chartQuery, hostRef, replayCursorIndex, replayMode,
    replaySelectionIndex, replayStartIndex, restartReplaySession, setReplayCursorIndex, setReplayMarkerX,
    setReplayMode, setReplayPlaying, setReplaySelectionIndex, setReplaySelectionX, setReplayStartIndex,
  } = ws;

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;

    // React delegates wheel events through a passive listener in this setup.
    // Use a native non-passive listener because chart zoom intentionally
    // consumes the wheel event so the page does not scroll underneath it.
    const handleChartWheel = (event: WheelEvent) => {
      const targetAdapter = adapterRef.current;
      if (!targetAdapter) return;
      event.preventDefault();
      event.stopPropagation();
      const bounds = host.getBoundingClientRect();
      const x = event.clientX - bounds.left;
      const y = event.clientY - bounds.top;
      if (targetAdapter.isPriceScaleCoordinate(x)) {
        targetAdapter.zoomPriceScaleAtCoordinate(y, event.deltaY);
        return;
      }
      if (event.deltaX !== 0) {
        targetAdapter.panTimeByPixels(-event.deltaX);
        return;
      }
      if (event.shiftKey) {
        targetAdapter.zoomPriceScaleAtCoordinate(y, event.deltaY);
        return;
      }
      targetAdapter.zoomAtCoordinate(x, event.deltaY);
    };

    host.addEventListener('wheel', handleChartWheel, { capture: true, passive: false });
    return () => host.removeEventListener('wheel', handleChartWheel, true);
  }, [adapter, adapterRef, hostRef]);

  const handleReplayStageClick = (event: React.MouseEvent<HTMLDivElement>) => {
    if (!replayMode || !active || !adapter || allBarsRef.current.length === 0) return;
    // A chart click chooses a new replay start only after the user explicitly
    // enters Select bar mode. Normal clicks during an active replay must not
    // restart the session and discard its simulated positions.
    if (replayCursorIndex !== null) return;
    const target = event.target as Element;
    if (target.closest('button, input, select, textarea, [role="dialog"], .trading-drawing-overlay')) return;
    const bounds = event.currentTarget.getBoundingClientRect();
    const x = event.clientX - bounds.left;
    if (adapter.isPriceScaleCoordinate(x)) return;
    const index = adapter.barIndexAtCoordinate(x, allBarsRef.current.length);
    if (index === null) return;
    setReplayPlaying(false);
    restartReplaySession();
    setReplaySelectionIndex(index);
    setReplayStartIndex(index);
    setReplayCursorIndex(index);
  };

  const resetReplay = () => {
    if (replayStartIndex === null) return;
    setReplayPlaying(false);
    restartReplaySession();
    setReplayCursorIndex(replayStartIndex);
  };

  const previousReplayBar = () => {
    if (replayCursorIndex === null || replayStartIndex === null || replayCursorIndex <= replayStartIndex) return;
    setReplayPlaying(false);
    restartReplaySession();
    setReplayCursorIndex(Math.max(replayStartIndex, replayCursorIndex - 1));
  };

  const exitReplay = () => {
    setReplayPlaying(false);
    setReplayMode(false);
  };

  useEffect(() => {
    if (!adapter || !replayMode || !active || replayStartIndex === null) {
      setReplayMarkerX(null);
      return;
    }
    const updateMarker = () => {
      const startBar = allBarsRef.current[replayStartIndex];
      setReplayMarkerX(startBar
        ? adapter.barTimeToCoordinate(startBar.start_time) ?? adapter.timeToCoordinate(startBar.start_time)
        : null);
    };
    const frame = window.requestAnimationFrame(updateMarker);
    window.addEventListener('resize', updateMarker);
    const host = hostRef.current;
    const observer = typeof ResizeObserver === 'undefined' || !host ? null : new ResizeObserver(updateMarker);
    observer?.observe(host as Element);
    const unsubscribeViewport = adapter.onViewportChange(updateMarker);
    return () => {
      window.cancelAnimationFrame(frame);
      window.removeEventListener('resize', updateMarker);
      observer?.disconnect();
      unsubscribeViewport();
    };
  }, [active, adapter, replayCursorIndex, replayMode, replayStartIndex, allBarsRef, hostRef, setReplayMarkerX]);

  useEffect(() => {
    const selecting = replayMode && active && replayCursorIndex === null;
    if (!selecting || !adapter || allBarsRef.current.length === 0) {
      setReplaySelectionX(null);
      setReplaySelectionIndex(null);
      return;
    }
    if (replaySelectionIndex === null || replaySelectionIndex >= allBarsRef.current.length) {
      const initialIndex = replayStartIndex ?? adapter.barIndexAtCoordinate(
        adapter.indicatorPlotWidth() / 2,
        allBarsRef.current.length,
      );
      setReplaySelectionIndex(initialIndex);
      return;
    }
    const updateDivider = () => {
      const bar = allBarsRef.current[replaySelectionIndex];
      setReplaySelectionX(bar
        ? adapter.barTimeToCoordinate(bar.start_time) ?? adapter.timeToCoordinate(bar.start_time)
        : null);
    };
    updateDivider();
    window.addEventListener('resize', updateDivider);
    const host = hostRef.current;
    const observer = typeof ResizeObserver === 'undefined' || !host ? null : new ResizeObserver(updateDivider);
    observer?.observe(host as Element);
    const unsubscribeViewport = adapter.onViewportChange(updateDivider);
    return () => {
      window.removeEventListener('resize', updateDivider);
      observer?.disconnect();
      unsubscribeViewport();
    };
  }, [active, adapter, chartQuery.data, replayCursorIndex, replayMode, replaySelectionIndex, replayStartIndex, allBarsRef, hostRef, setReplaySelectionIndex, setReplaySelectionX]);

  return {
    handleReplayStageClick, resetReplay, previousReplayBar, exitReplay,
  };
}
