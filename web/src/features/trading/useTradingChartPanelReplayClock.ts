import { useEffect, useMemo, useRef, useState } from 'react';
import { formingBar, loadIntrabars, MAX_INTRABAR_BARS } from './intrabarData';
import { barCloseTime, replaySubBarStepMs, replayTickPlan, replayVisibleCount } from './replayClock';
import { tradingIntervalDurationMs } from './tradingIntervals';
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
  /** The chart's instrument and interval, for sub-bar playback's intrabar data (TVP-8.1). */
  instrumentId?: string;
  interval?: string;
};

/** Sub-bar playback's lower bars for one chart, by chunk start (ms): a range of whole chart bars one request covers. */
type IntrabarChunks = Map<number, readonly MarketBar[] | 'loading'>;

/**
 * The chart's forming bar at the clock in sub-bar playback (TVP-8.1): the next bar after the closed ones, built from
 * the lower bars that closed by then. Null in bar-by-bar playback, or until its intrabar data loads.
 */
function useReplayFormingBar(input: { replay: boolean; active: boolean; bars: readonly MarketBar[]; instrumentId?: string; bindingId: string | null; interval?: string }): MarketBar | null {
  const { replay, active, bars, instrumentId, bindingId, interval } = input;
  const [forming, setForming] = useState<MarketBar | null>(null);
  useEffect(() => {
    setForming(null);
    if (!replay || !instrumentId || !interval) return;
    const chunks: IntrabarChunks = new Map();
    let cancelled = false;
    const update = () => {
      const { clock, updateInterval } = useTradingReplayStore.getState();
      const stepMs = replaySubBarStepMs(interval, updateInterval);
      const chartMs = tradingIntervalDurationMs(interval);
      const next = clock === null ? undefined : bars[replayVisibleCount(bars, clock)];
      const start = next ? Date.parse(next.start_time) : Number.NaN;
      if (clock === null || stepMs === null || chartMs === null || !next || !(start < clock)) {
        setForming(null);
        return;
      }
      // Whole chart bars that one request covers, aligned so every bar of a chunk asks for the same range.
      const chunkMs = Math.max(chartMs, Math.floor((MAX_INTRABAR_BARS * stepMs) / chartMs) * chartMs);
      const chunkStart = Math.floor(start / chunkMs) * chunkMs;
      const chunk = chunks.get(chunkStart);
      if (chunk === undefined) {
        chunks.set(chunkStart, 'loading');
        const lowerInterval = updateInterval!;
        loadIntrabars({ instrumentId, bindingId, interval, lowerInterval, start: chunkStart, end: chunkStart + chunkMs }).then((response) => {
          if (cancelled) return;
          chunks.set(chunkStart, response.bars as MarketBar[]);
          if (active) {
            useTradingReplayStore.getState().setIntrabarNote(response.complete ? null
              : response.available_from ? `${lowerInterval} data starts ${new Date(response.available_from).toLocaleString()}` : `No ${lowerInterval} data here`);
          }
          update();
        }).catch(() => {
          if (!cancelled) chunks.set(chunkStart, []);
        });
        return;
      }
      if (chunk === 'loading') return;
      const end = start + chartMs;
      const lower = chunk.filter((bar) => {
        const time = Date.parse(bar.start_time);
        return time >= start && time < end;
      });
      setForming(formingBar(next, lower, clock));
    };
    update();
    const unsubscribe = useTradingReplayStore.subscribe((state, previous) => {
      if (state.clock !== previous.clock || state.updateInterval !== previous.updateInterval) update();
    });
    return () => {
      cancelled = true;
      unsubscribe();
    };
  }, [active, bars, bindingId, instrumentId, interval, replay]);
  return forming;
}

/**
 * One chart's view of the shared replay clock (TVP-8.1).
 *
 * Every chart derives what it shows from the clock. A chart re-renders only
 * when its own visible bar count changes, not on every playback tick. The
 * active chart also feeds the clock: it publishes its bars (which step and
 * play advance through) and runs the playback ticker.
 */
export function useChartReplayClock({ active, replayMode, bars, chartKey, bindingId = null, reloadBars, instrumentId, interval }: ChartReplayClockInput) {
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
  const forming = useReplayFormingBar({ replay: visible, active, bars, instrumentId, bindingId, interval });
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
    /** The forming bar after the visible ones in sub-bar playback (TVP-8.1). */
    replayFormingBar: visible && forming && forming.start_time === bars[visibleBarCount]?.start_time ? forming : null,
    replayCurrentBar: currentBar,
    replayStartBar: startBar,
    replayStartTime: startTime,
    replayHasNextBar: hasNextBar,
    replayHasPreviousBar: visible && hasPreviousBar,
    replayPlaying: playing,
  };
}
