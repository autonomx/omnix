import { create } from 'zustand';
import type { PaperAccountSnapshot } from './paperTypes';
import {
  DEFAULT_REPLAY_SPEED,
  nextReplayClock,
  previousReplayClock,
  type ReplaySpeed,
} from './replayClock';
import { useTradingStore } from './tradingStore';
import type { MarketBar } from './tradingTypes';

/**
 * Bar replay state shared by every chart in the layout (TVP-8.1).
 *
 * Replay mode and the trading session id live in the workspace store; the
 * clock lives here because it changes on every playback tick and the
 * workspace store is saved on every change.
 *
 * The step, play and select actions work without a chart panel, so a command
 * or hotkey layer (TVP-0.3) can call them through `getState()`.
 */
type TradingReplayState = {
  /** The active chart's bar at the clock, which replay trading executes against. */
  bar: MarketBar | null;
  snapshot: PaperAccountSnapshot | null;
  /** The replay clock in epoch milliseconds; null until a start bar is chosen. */
  clock: number | null;
  /** The clock at the chosen start bar; reset and step back stop here. */
  startTime: number | null;
  /** The active chart is waiting for a click that chooses the start bar. */
  selecting: boolean;
  playing: boolean;
  speed: ReplaySpeed;
  /** The active chart's bars, which step and play advance through. */
  activeBars: readonly MarketBar[];
  setBar: (bar: MarketBar | null) => void;
  setSnapshot: (snapshot: PaperAccountSnapshot | null) => void;
  setSpeed: (speed: ReplaySpeed) => void;
  setActiveBars: (bars: readonly MarketBar[]) => void;
  setPlaying: (playing: boolean) => void;
  togglePlaying: () => void;
  /** Start replay at `time` (a bar's close) and restart the replay trading session. */
  chooseStart: (time: number) => void;
  /** Pause and let the active chart choose a new start bar (jump to bar). */
  beginSelecting: () => void;
  /** Move the clock forward by `steps` bars of the active chart; false when there is no later bar. */
  stepForward: (steps?: number) => boolean;
  /** Move the clock back one bar of the active chart, not before the start. */
  stepBack: () => boolean;
  resetToStart: () => void;
  /** Leave replay: forget the clock, bar and simulated account; the speed is kept. */
  clear: () => void;
};

const NO_BARS: readonly MarketBar[] = [];

function restartTradingSession(): void {
  useTradingStore.getState().restartReplaySession();
}

export const useTradingReplayStore = create<TradingReplayState>((set, get) => ({
  bar: null,
  snapshot: null,
  clock: null,
  startTime: null,
  selecting: true,
  playing: false,
  speed: DEFAULT_REPLAY_SPEED,
  activeBars: NO_BARS,
  setBar: (bar) => set({ bar }),
  setSnapshot: (snapshot) => set({ snapshot }),
  setSpeed: (speed) => set({ speed }),
  setActiveBars: (activeBars) => set({ activeBars }),
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
    return true;
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
  clear: () => set({
    bar: null,
    snapshot: null,
    clock: null,
    startTime: null,
    selecting: true,
    playing: false,
    activeBars: NO_BARS,
  }),
}));
