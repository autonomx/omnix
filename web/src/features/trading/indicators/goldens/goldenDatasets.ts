import type { MarketBar } from '../../tradingTypes';
import { fixture } from '../../../../test/fixture';

export type GoldenBar = {
  start_time: string;
  end_time: string;
  open: string;
  high: string;
  low: string;
  close: string;
  volume: string;
};

export type GoldenDataset = { name: string; bars: GoldenBar[] };

const HOUR_MS = 3_600_000;
const FIRST_BAR_MS = Date.parse('2026-01-05T14:00:00Z');

function mulberry32(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let t = state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function gaussian(random: () => number): number {
  const u = Math.max(random(), 1e-12);
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * random());
}

function bar(index: number, open: number, high: number, low: number, close: number, volume: number): GoldenBar {
  const start = FIRST_BAR_MS + index * HOUR_MS;
  return {
    start_time: new Date(start).toISOString(),
    end_time: new Date(start + HOUR_MS).toISOString(),
    open: open.toFixed(2),
    high: high.toFixed(2),
    low: low.toFixed(2),
    close: close.toFixed(2),
    volume: Math.round(volume).toString(),
  };
}

function randomWalk(seed: number, length: number, gapEvery = 0): GoldenBar[] {
  const random = mulberry32(seed);
  const bars: GoldenBar[] = [];
  let previousClose = 100;
  for (let index = 0; index < length; index += 1) {
    const gap = gapEvery > 0 && index > 0 && index % gapEvery === 0 ? (random() < 0.5 ? -1 : 1) * (3 + random() * 3) : 0;
    const open = Math.max(5, previousClose + gap + gaussian(random) * 0.2);
    const close = Math.max(5, open + gaussian(random) * 0.8);
    const high = Math.max(open, close) + random() * 0.6;
    const low = Math.max(1, Math.min(open, close) - random() * 0.6);
    bars.push(bar(index, open, high, low, close, 1_000 + random() * 5_000));
    previousClose = close;
  }
  return bars;
}

function gapsFlatsAndZeroVolume(): GoldenBar[] {
  const bars = randomWalk(0x5eed2, 160, 25);
  for (let index = 40; index < 50; index += 1) {
    const price = bars[39].close;
    bars[index] = { ...bars[index], open: price, high: price, low: price, close: price, volume: '0' };
  }
  for (let index = 90; index < 100; index += 1) bars[index] = { ...bars[index], volume: '0' };
  bars[120] = { ...bars[120], high: (Number(bars[120].high) + 15).toFixed(2) };
  return bars;
}

function trendUp(length: number): GoldenBar[] {
  return Array.from({ length }, (_, index) => {
    const close = 50 + index * 0.5;
    const open = close - 0.3;
    return bar(index, open, close + 0.2, open - 0.2, close, 1_000 + index);
  });
}

function constant(length: number): GoldenBar[] {
  return Array.from({ length }, (_, index) => bar(index, 100, 100, 100, 100, 500));
}

export const GOLDEN_DATASETS: readonly GoldenDataset[] = [
  { name: 'random-walk-300', bars: randomWalk(0x5eed1, 300) },
  { name: 'gaps-flats-zero-volume-160', bars: gapsFlatsAndZeroVolume() },
  { name: 'short-12', bars: randomWalk(0x5eed3, 12) },
  { name: 'trend-up-80', bars: trendUp(80) },
  { name: 'constant-40', bars: constant(40) },
];

export const VARIANT_DATASET = 'random-walk-300';

export function asMarketBars(dataset: GoldenDataset): MarketBar[] {
  return fixture<MarketBar[]>(dataset.bars.map((item) => ({
    ...item,
    instrument_id: 'golden:test',
    interval: '1h',
    is_final: true,
  })));
}
