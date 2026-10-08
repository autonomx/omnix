import { create } from 'zustand';
import type { PaperAccountSnapshot, PaperOrderInput } from './paperTypes';
import {
  barCloseTime,
  DEFAULT_REPLAY_SPEED,
  nextReplayClock,
  previousReplayClock,
  replayVisibleCount,
  type ReplaySpeed,
} from './replayClock';
import { advanceReplaySnapshot, placeReplayOrder } from './replayTrading';
import { useTradingStore } from './tradingStore';
import type { MarketBar } from './tradingTypes';

export type ReplayOrderResult = Awaited<ReturnType<typeof placeReplayOrder>>;

/**
 * Bar replay state shared by every chart in the layout (TVP-8.1).
 *
 * Replay mode and the trading session id live in the workspace store; the
 * clock lives here because it changes on every playback tick and the
 * workspace store is saved on every change.
 *
 * The replay account is advanced here too, not in the order ticket (which
 * may be hidden): every active-chart bar the clock passes is sent to the
 * server execution kernel once, in order, one request at a time, each built
 * on the previous result. Orders join the same queue.
 *
 * The step, play and select actions work without a chart panel, so a command
 * or hotkey layer (TVP-0.3) can call them through `getState()`.
 */
type TradingReplayState = {
  /** The active chart's bar at the clock; the price replay orders use. */
  bar: MarketBar | null;
  /** The simulated replay account. */
  snapshot: PaperAccountSnapshot | null;
  /** The replay clock in epoch milliseconds; null until a start bar is chosen. */
  clock: number | null;
  /** The clock at the chosen start bar; reset and step back stop here. */
  startTime: number | null;
  /** The active chart is waiting for a click that chooses the start bar. */
  selecting: boolean;
  playing: boolean;
  speed: ReplaySpeed;
  /** The active chart's bars, which step, play and the replay account advance through. */
  activeBars: readonly MarketBar[];
  /** The active chart's instrument, binding and interval; a change restarts replay trading. */
  activeChartKey: string | null;
  /** The close of the last bar the replay account has been advanced through. */
  advancedThrough: number | null;
  /** Replay account requests (bar advances and orders) not yet finished. */
  pendingExecutions: number;
  executionError: string | null;
  setBar: (bar: MarketBar | null) => void;
  /** Replace the replay account outright (tests and recovery); prefer seedSnapshot and placeOrder. */
  setSnapshot: (snapshot: PaperAccountSnapshot | null) => void;
  /**
   * Start the replay account at the current clock. A repeated call with the
   * same key keeps the existing account, so remounting the order ticket does
   * not discard simulated orders.
   */
  seedSnapshot: (snapshot: PaperAccountSnapshot, key: string) => void;
  /** Place a replay order after every queued bar advance, at the current bar. */
  placeOrder: (input: PaperOrderInput) => Promise<ReplayOrderResult>;
  setSpeed: (speed: ReplaySpeed) => void;
  setActiveBars: (bars: readonly MarketBar[]) => void;
  /** Record the active chart's identity; a different instrument, binding or interval restarts replay trading. */
  setActiveChartKey: (key: string) => void;
  setPlaying: (playing: boolean) => void;
  togglePlaying: () => void;
  /** Start replay at `time` (a bar's close) and restart the replay trading session. */
  chooseStart: (time: number) => void;
  /** Pause and let the active chart choose a new start bar (jump to bar). */
  beginSelecting: () => void;
  /** Move the clock forward by `steps` bars of the active chart; false when there is no later bar. */
  stepForward: (steps?: number) => boolean;
  /**
   * One playback tick. It waits (returns false) while the replay account has
   * working orders or positions and earlier bars are still being advanced, so
   * the clock never runs ahead of the account.
   */
  playbackTick: (steps: number) => boolean;
  /** Move the clock back one bar of the active chart, not before the start. */
  stepBack: () => boolean;
  resetToStart: () => void;
  /** Drop the replay account and its queue (a new replay trading session). */
  resetExecution: () => void;
  /** Leave replay: forget the clock, bar and simulated account; the speed is kept. */
  clear: () => void;
};

const NO_BARS: readonly MarketBar[] = [];

class ReplayRestartedError extends Error {
  constructor() {
    super('Replay restarted before the request ran.');
  }
}

/** The replay account's request queue; `generation` changes whenever queued work must be dropped. */
const execution = {
  generation: 0,
  chain: Promise.resolve() as Promise<unknown>,
  enqueuedThrough: null as number | null,
  seedKey: null as string | null,
};

function restartTradingSession(): void {
  useTradingStore.getState().restartReplaySession();
}

/** Whether the replay account has anything a bar could fill or move. */
export function replayAccountHasExposure(snapshot: PaperAccountSnapshot | null): boolean {
  if (!snapshot) return false;
  return snapshot.open_orders.length > 0 || snapshot.positions.some((position) => Number(position.quantity) !== 0);
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
}

function resetExecution(): void {
  execution.generation += 1;
  execution.chain = Promise.resolve();
  execution.enqueuedThrough = null;
  execution.seedKey = null;
  useTradingReplayStore.setState({ snapshot: null, advancedThrough: null, pendingExecutions: 0, executionError: null });
}

export const useTradingReplayStore = create<TradingReplayState>((set, get) => {
  /** Run `work` on the replay account after everything already queued. */
  const enqueue = <T>(
    work: (snapshot: PaperAccountSnapshot) => Promise<{ snapshot: PaperAccountSnapshot; value: T; through?: number }>,
  ): Promise<T> => {
    const generation = execution.generation;
    set((state) => ({ pendingExecutions: state.pendingExecutions + 1 }));
    const task = execution.chain.then(async () => {
      if (generation !== execution.generation) throw new ReplayRestartedError();
      const snapshot = get().snapshot;
      if (!snapshot) throw new Error('Replay account is still loading.');
      const result = await work(snapshot);
      if (generation !== execution.generation) throw new ReplayRestartedError();
      set(result.through === undefined
        ? { snapshot: result.snapshot }
        : { snapshot: result.snapshot, advancedThrough: result.through });
      return result.value;
    }).finally(() => {
      if (generation === execution.generation) set((state) => ({ pendingExecutions: Math.max(0, state.pendingExecutions - 1) }));
    });
    execution.chain = task.catch(() => undefined);
    return task;
  };

  /** Queue an advance for every active-chart bar the clock has passed since the last one. */
  const advanceToClock = () => {
    const { activeBars, clock, snapshot } = get();
    const from = execution.enqueuedThrough;
    if (!snapshot || clock === null || from === null || clock <= from) return;
    const bars = activeBars.slice(replayVisibleCount(activeBars, from), replayVisibleCount(activeBars, clock));
    execution.enqueuedThrough = clock;
    for (const bar of bars) {
      const through = barCloseTime(bar);
      void enqueue(async (current) => ({ snapshot: await advanceReplaySnapshot(current, bar), value: undefined, through }))
        .catch((error: unknown) => {
          if (error instanceof ReplayRestartedError) return;
          // Drop the rest of the queue and resume from the last advanced bar on the next step.
          execution.generation += 1;
          execution.chain = Promise.resolve();
          execution.enqueuedThrough = get().advancedThrough;
          set({ pendingExecutions: 0, playing: false, executionError: errorMessage(error, 'Replay execution failed.') });
        });
    }
  };

  return {
    bar: null,
    snapshot: null,
    clock: null,
    startTime: null,
    selecting: true,
    playing: false,
    speed: DEFAULT_REPLAY_SPEED,
    activeBars: NO_BARS,
    activeChartKey: null,
    advancedThrough: null,
    pendingExecutions: 0,
    executionError: null,
    setBar: (bar) => set({ bar }),
    setSnapshot: (snapshot) => set({ snapshot }),
    seedSnapshot: (snapshot, key) => {
      if (execution.seedKey === key && get().snapshot) return;
      execution.generation += 1;
      execution.chain = Promise.resolve();
      execution.seedKey = key;
      execution.enqueuedThrough = get().clock;
      set({ snapshot, advancedThrough: get().clock, pendingExecutions: 0, executionError: null });
    },
    placeOrder: (input) => {
      const bar = get().bar;
      if (!bar) return Promise.reject(new Error('Select a replay bar before trading.'));
      return enqueue(async (snapshot) => {
        const result = await placeReplayOrder(snapshot, input, bar);
        return { snapshot: result.snapshot, value: result };
      });
    },
    setSpeed: (speed) => set({ speed }),
    setActiveBars: (activeBars) => set({ activeBars }),
    setActiveChartKey: (key) => {
      const previous = get().activeChartKey;
      if (previous === key) return;
      set({ activeChartKey: key });
      if (previous === null) return;
      get().setPlaying(false);
      restartTradingSession();
    },
    setPlaying: (playing) => {
      const state = get();
      if (!playing) {
        if (state.playing) set({ playing: false });
        return;
      }
      if (state.clock === null || state.selecting) return;
      if (nextReplayClock(state.activeBars, state.clock) === null) return;
      set({ playing: true });
    },
    togglePlaying: () => get().setPlaying(!get().playing),
    chooseStart: (time) => {
      set({ clock: time, startTime: time, selecting: false, playing: false });
      restartTradingSession();
    },
    beginSelecting: () => set({ selecting: true, playing: false }),
    stepForward: (steps = 1) => {
      const { activeBars, clock, playing, selecting } = get();
      if (clock === null || selecting) return false;
      const next = nextReplayClock(activeBars, clock, steps);
      if (next === null) {
        if (playing) set({ playing: false });
        return false;
      }
      // Playback stops on the active chart's last bar.
      set({ clock: next, playing: playing && nextReplayClock(activeBars, next) !== null });
      advanceToClock();
      return true;
    },
    playbackTick: (steps) => {
      const { pendingExecutions, snapshot } = get();
      if (pendingExecutions > 0 && replayAccountHasExposure(snapshot)) return false;
      return get().stepForward(steps);
    },
    stepBack: () => {
      const { activeBars, clock, selecting, startTime } = get();
      if (clock === null || startTime === null || selecting) return false;
      const previous = previousReplayClock(activeBars, clock, startTime);
      if (previous === null) return false;
      set({ clock: previous, playing: false });
      restartTradingSession();
      return true;
    },
    resetToStart: () => {
      const { startTime } = get();
      if (startTime === null) return;
      set({ clock: startTime, selecting: false, playing: false });
      restartTradingSession();
    },
    resetExecution,
    clear: () => {
      resetExecution();
      set({
        bar: null,
        clock: null,
        startTime: null,
        selecting: true,
        playing: false,
        activeBars: NO_BARS,
        activeChartKey: null,
      });
    },
  };
});

// A new replay trading session (restart, new start bar, tab switch, entering
// replay) starts from a fresh account: queued work for the old one is dropped.
useTradingStore.subscribe((state, previous) => {
  if (state.replaySessionId !== previous.replaySessionId) useTradingReplayStore.getState().resetExecution();
});
