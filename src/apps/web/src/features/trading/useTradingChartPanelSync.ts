import { useEffect } from 'react';
import { normalizeChartBars } from './chart/chartAdapter';
import { indicatorUsesSeparatePane } from './indicators/coreIndicators';
import type { MarketBar } from './tradingTypes';
import { TradingChartPanelProps, applyVisibleRange } from './tradingChartPanelModel';
import type { useChartPanelState } from './useTradingChartPanelState';
import type { useChartIndicatorScheduling } from './useTradingChartPanelData';
import type { useChartPanelData } from './useTradingChartPanelData';
import type { useChartLifecycle } from './useTradingChartPanelLifecycle';
import { startTicker } from '../../shared/timers';

/** Keeps the chart in step with its data, replay, chart type, indicators and comparisons. */
export function useChartSync(ws: TradingChartPanelProps & ReturnType<typeof useChartPanelState> & ReturnType<typeof useChartIndicatorScheduling> & ReturnType<typeof useChartPanelData> & ReturnType<typeof useChartLifecycle>) {
  const {
    active, adapter, adapterRef, allBarsRef, barsRef, bindingId, chartQuery, chartType, clearReplayState, drawings,
    fittedBarsKeyRef, forceLiveRender, fullscreenIndicator, fullscreenMainPane, historyLimit, hostRef, indicators,
    indicatorsRef, instrumentId, interval, minimizedIndicators, pendingIntervalScrollRef, pendingRangeIntervalRef,
    refreshIndicatorPanes, replayCurrentBar, replayCursorIndex, replayMode, replayPlaying, replaySessionId,
    replaySpeed, replayStartIndex, replayVisible, replayWasVisibleRef, restartReplaySession, rightOffset,
    scheduleIndicators, selectedDrawing, selectedRangeRef, selectedTimezone, setReplayBar, setReplayCursorIndex,
    setReplayPlaying, setReplayStartIndex, setSelectedRangeLabel, streamDataKeyRef, streamRevisionRef, timezoneId,
  } = ws;

  useEffect(() => {
    const bars = normalizeChartBars((chartQuery.data?.bars ?? []) as MarketBar[]);
    allBarsRef.current = bars;
    const previousDataIdentity = streamDataKeyRef.current?.split('|').slice(0, 2).join('|') ?? null;
    const dataKey = chartQuery.data
      ? `${chartQuery.data.instrument.instrument_id}|${chartQuery.data.binding.binding_id}|${chartQuery.data.interval}|${historyLimit}`
      : null;
    if (dataKey !== null && dataKey !== streamDataKeyRef.current) {
      streamDataKeyRef.current = dataKey;
      streamRevisionRef.current = Math.max(
        1,
        ...bars.map((bar) => Number(bar.ingestion_revision) || 1),
      );
    }
    forceLiveRender((value) => value + 1);
    const dataChanged = dataKey !== null && dataKey !== fittedBarsKeyRef.current;
    const replayViewChanged = replayWasVisibleRef.current !== replayVisible;
    replayWasVisibleRef.current = replayVisible;
    // Selecting a replay bar replaces the data with the historical prefix,
    // but must preserve the pre-click logical range. Fitting that prefix would
    // move the selected bar to the right edge instead of leaving it where the
    // user clicked. Fit only when loading new data or returning to live mode.
    const shouldFit = dataChanged || (replayViewChanged && !replayVisible);
    const currentDataIdentity = dataKey?.split('|').slice(0, 2).join('|') ?? null;
    const keepCustomRange = typeof selectedRangeRef.current === 'object'
      && selectedRangeRef.current !== null
      && previousDataIdentity !== null
      && previousDataIdentity === currentDataIdentity;
    const keepSelectedRange = dataChanged && (pendingRangeIntervalRef.current === interval || keepCustomRange);
    if (dataChanged && !keepSelectedRange) {
      selectedRangeRef.current = undefined;
      setSelectedRangeLabel('All');
    }
    const visibleBars = replayVisible
      ? bars.slice(0, Math.min(bars.length, (replayCursorIndex ?? 0) + 1))
      : bars;
    barsRef.current = visibleBars;
    adapterRef.current?.setBars(visibleBars, shouldFit);
    if (keepSelectedRange && selectedRangeRef.current !== undefined && visibleBars.length > 0 && adapterRef.current) {
      applyVisibleRange(adapterRef.current.api(), selectedRangeRef.current, visibleBars, interval, rightOffset, selectedTimezone);
    }
    if (pendingIntervalScrollRef.current && dataChanged && visibleBars.length > 0 && adapterRef.current) {
      adapterRef.current.scrollToLatest();
      pendingIntervalScrollRef.current = false;
    }
    if (keepSelectedRange) pendingRangeIntervalRef.current = null;
    if (dataKey !== null && bars.length > 0) fittedBarsKeyRef.current = dataKey;
    scheduleIndicators();
    // Keyed by timezoneId and the loaded data, not by values derived from them (selectedTimezone, historyLimit).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, chartQuery.data, interval, replayCursorIndex, replayMode, replayStartIndex, replayVisible, rightOffset, scheduleIndicators, timezoneId, adapterRef, allBarsRef, barsRef, fittedBarsKeyRef, forceLiveRender, pendingIntervalScrollRef, pendingRangeIntervalRef, replayWasVisibleRef, selectedRangeRef, setSelectedRangeLabel, streamDataKeyRef, streamRevisionRef]);

  useEffect(() => {
    setReplayStartIndex(null);
    setReplayCursorIndex(null);
    setReplayPlaying(false);
    if (replayMode && active) restartReplaySession();
  }, [active, bindingId, instrumentId, interval, replayMode, restartReplaySession, setReplayCursorIndex, setReplayPlaying, setReplayStartIndex]);

  useEffect(() => {
    if (!replayMode || !active) {
      if (!replayMode && active) clearReplayState();
      return;
    }
    setReplayBar(replayCurrentBar);
    // Publishes the bar at the replay cursor; replayCursorIndex stands for replayCurrentBar.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, clearReplayState, replayCursorIndex, replayMode, replaySessionId, setReplayBar]);

  useEffect(() => {
    if (!replayMode || !active) {
      setReplayPlaying(false);
      return;
    }
    if (replayCursorIndex === null || replayCursorIndex >= allBarsRef.current.length - 1) {
      setReplayPlaying(false);
    }
  }, [active, replayCursorIndex, replayMode, allBarsRef, setReplayPlaying]);

  useEffect(() => {
    if (!replayPlaying || !replayVisible || replayCursorIndex === null) return;
    const numericSpeed = Math.max(0.25, Math.min(8, Number(replaySpeed) || 1));
    return startTicker(() => {
      setReplayCursorIndex((current) => {
        const lastIndex = allBarsRef.current.length - 1;
        if (current === null || current >= lastIndex) {
          setReplayPlaying(false);
          return current;
        }
        return current + 1;
      });
    }, Math.max(100, 1_000 / numericSpeed));
  }, [replayCursorIndex, replayPlaying, replaySpeed, replayVisible, allBarsRef, setReplayCursorIndex, setReplayPlaying]);

  useEffect(() => {
    adapterRef.current?.setChartType(chartType, barsRef.current);
    if (selectedRangeRef.current !== undefined && barsRef.current.length > 0 && adapterRef.current) {
      applyVisibleRange(adapterRef.current.api(), selectedRangeRef.current, barsRef.current, interval, rightOffset, selectedTimezone);
    }
    // Keyed by timezoneId, not by the selectedTimezone derived from it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chartType, interval, rightOffset, timezoneId, adapterRef, barsRef, selectedRangeRef]);

  useEffect(() => {
    indicatorsRef.current = indicators;
    scheduleIndicators();
  }, [indicators, scheduleIndicators, indicatorsRef]);

  useEffect(() => {
    if (!active) return;
    const handleDrawingKeyboard = (event: KeyboardEvent) => {
      const target = event.target;
      if (target instanceof HTMLElement && target.closest('input, textarea, select, [contenteditable="true"]')) return;
      const key = event.key.toLowerCase();
      if ((event.metaKey || event.ctrlKey) && !event.altKey && key === 'z') {
        event.preventDefault();
        event.stopPropagation();
        if (event.shiftKey) drawings.redo();
        else drawings.undo();
        return;
      }
      if (!selectedDrawing || (event.key !== 'Delete' && event.key !== 'Backspace')) return;
      event.preventDefault();
      event.stopPropagation();
      drawings.removeSelected();
    };
    window.addEventListener('keydown', handleDrawingKeyboard);
    return () => window.removeEventListener('keydown', handleDrawingKeyboard);
  }, [active, drawings, selectedDrawing]);

  useEffect(() => {
    const targetAdapter = adapterRef.current;
    if (!targetAdapter) return;
    if (fullscreenIndicator) {
      targetAdapter.setIndicatorPaneFullscreen(fullscreenIndicator);
    } else if (fullscreenMainPane) {
      targetAdapter.setMainPaneFullscreen(true);
    } else {
      for (const indicator of indicators) {
        if (indicatorUsesSeparatePane(indicator.id)) {
          targetAdapter.setIndicatorPaneMinimized(indicator.id, minimizedIndicators.has(indicator.id));
        }
      }
    }
    refreshIndicatorPanes(targetAdapter);
    const frame = window.requestAnimationFrame(() => refreshIndicatorPanes(targetAdapter));
    return () => window.cancelAnimationFrame(frame);
  }, [adapter, fullscreenIndicator, fullscreenMainPane, indicators, minimizedIndicators, refreshIndicatorPanes, adapterRef]);

  useEffect(() => {
    if (!adapter) return;
    const refresh = () => {
      try {
        adapter.refreshIndicatorPaneFullscreen();
      } catch {
        // The adapter may be disposed during a chart switch.
      }
      const frame = window.requestAnimationFrame(() => refreshIndicatorPanes(adapter));
      return frame;
    };
    refresh();
    window.addEventListener('resize', refresh);
    const host = hostRef.current;
    const observer = typeof ResizeObserver === 'undefined' || !host ? null : new ResizeObserver(refresh);
    if (observer && host) observer.observe(host);
    return () => {
      window.removeEventListener('resize', refresh);
      observer?.disconnect();
    };
  }, [adapter, refreshIndicatorPanes, hostRef]);

  return {

  };
}
