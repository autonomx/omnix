import { useEffect, useMemo, useRef } from 'react';
import { barCloseTime, replayTickPlan, replayVisibleCount } from './replayClock';
import { useTradingReplayStore } from './tradingReplayStore';
import type { MarketBar } from './tradingTypes';
import { startTicker } from '../../shared/timers';

export type ChartReplayClockInput = {
  active: boolean;
  replayMode: boolean;
  /** The chart's loaded bars, normalized and time-ordered. */
  bars: readonly MarketBar[];
  /** The chart's instrument, binding and interval. */
  chartKey: string;
  /** The feed binding the chart's bars come from; replay trading on this chart uses it. */
  bindingId?: string | null;
  /** Reloads the chart's bars; called when replay ends, since no chart streams during replay. */
  reloadBars: () => void;
};

/**
 * One chart's view of the shared replay clock (TVP-8.1).
 *
 * Every chart derives what it shows from the clock. A chart re-renders only
 * when its own visible bar count changes, not on every playback tick. The
 * active chart also feeds the clock: it publishes its bars (which step and
 * play advance through) and runs the playback ticker.
 */
export function useChartReplayClock({ active, replayMode, bars, chartKey, bindingId = null, reloadBars }: ChartReplayClockInput) {
  const selecting = useTradingReplayStore((state) => state.selecting);
  const clockSet = useTradingReplayStore((state) => state.clock !== null);
  const visibleBarCount = useTradingReplayStore((state) => (state.clock === null ? 0 : replayVisibleCount(bars, state.clock)));
  const startBarCount = useTradingReplayStore((state) => (state.startTime === null ? 0 : replayVisibleCount(bars, state.startTime)));
  const hasPreviousBar = useTradingReplayStore((state) => state.clock !== null && state.startTime !== null && state.clock > state.startTime);
  const startTime = useTradingReplayStore((state) => state.startTime);
  const playing = useTradingReplayStore((state) => state.playing);
  const speed = useTradingReplayStore((state) => state.speed);

  const choosingStart = replayMode && active && selecting;
  const visible = replayMode && clockSet && !choosingStart;
  const currentBar = replayMode && visibleBarCount > 0 ? bars[visibleBarCount - 1] ?? null : null;
  const startBar = replayMode && startBarCount > 0 ? bars[startBarCount - 1] ?? null : null;
  const hasNextBar = visible && visibleBarCount < bars.length;
  // Replay trading prices orders at the latest bar whose close is known.
  const tradableBar = useMemo(() => {
    if (!replayMode) return null;
    for (let index = visibleBarCount - 1; index >= 0; index -= 1) {
      if (Number.isFinite(barCloseTime(bars[index]))) return bars[index];
    }
    return null;
  }, [bars, replayMode, visibleBarCount]);

  // The active chart's identity decides whether replay trading restarts:
  // switching between charts of the same symbol, feed and interval keeps it.
  useEffect(() => {
    if (!replayMode || !active) return;
    useTradingReplayStore.getState().setActiveChartKey(chartKey);
  }, [active, chartKey, replayMode]);

  useEffect(() => {
    if (!active) return;
    const store = useTradingReplayStore.getState();
    if (!replayMode) {
      store.clear();
      return;
    }
    store.setActiveBars(bars, bindingId);
  }, [active, bars, bindingId, replayMode]);

  useEffect(() => {
    if (!replayMode || !active) return;
    useTradingReplayStore.getState().setBar(tradableBar);
  }, [active, replayMode, tradableBar]);

  useEffect(() => {
    if (!active || !playing || !visible) return;
    const { intervalMs, barsPerTick } = replayTickPlan(speed);
    // Sub-bar playback (after TVP-0.6) will tick the clock in smaller steps here.
    return startTicker(() => { useTradingReplayStore.getState().playbackTick(barsPerTick); }, intervalMs);
  }, [active, playing, speed, visible]);

  const wasReplayingRef = useRef(replayMode);
  useEffect(() => {
    // Bars that closed during replay were never streamed; reload them on the way back to real time.
    if (wasReplayingRef.current && !replayMode) reloadBars();
    wasReplayingRef.current = replayMode;
  }, [reloadBars, replayMode]);

  return {
    replayChoosingStart: choosingStart,
    replayVisible: visible,
    replayVisibleBarCount: replayMode ? visibleBarCount : 0,
    replayCurrentBar: currentBar,
    replayStartBar: startBar,
    replayStartTime: startTime,
    replayHasNextBar: hasNextBar,
    replayHasPreviousBar: visible && hasPreviousBar,
    replayPlaying: playing,
  };
}
