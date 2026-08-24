import { create } from 'zustand';
import type { PaperAccountSnapshot } from './paperTypes';
import type { MarketBar } from './tradingTypes';

type TradingReplayState = {
  bar: MarketBar | null;
  snapshot: PaperAccountSnapshot | null;
  setBar: (bar: MarketBar | null) => void;
  setSnapshot: (snapshot: PaperAccountSnapshot | null) => void;
  clear: () => void;
};

export const useTradingReplayStore = create<TradingReplayState>((set) => ({
  bar: null,
  snapshot: null,
  setBar: (bar) => set({ bar }),
  setSnapshot: (snapshot) => set({ snapshot }),
  clear: () => set({ bar: null, snapshot: null }),
}));
