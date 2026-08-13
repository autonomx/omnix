export type SpikeBar = {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  isFinal: boolean;
  ingestionRevision: number;
};

export type DrawingPoint = { time: number; price: number };
export type TrendDrawing = {
  id: string;
  start: DrawingPoint;
  end: DrawingPoint;
};

export function generateSpikeBars(count = 5_000, startTime = 1_700_000_000, intervalSeconds = 60): SpikeBar[] {
  const bars: SpikeBar[] = [];
  let close = 40_000;
  for (let index = 0; index < count; index += 1) {
    const wave = Math.sin(index / 37) * 42 + Math.cos(index / 11) * 18;
    const drift = index * 0.65;
    const open = close;
    close = 40_000 + drift + wave;
    bars.push({
      time: startTime + index * intervalSeconds,
      open,
      high: Math.max(open, close) + 14 + (index % 7),
      low: Math.min(open, close) - 13 - (index % 5),
      close,
      volume: 100 + ((index * 17) % 240),
      isFinal: true,
      ingestionRevision: 1,
    });
  }
  return bars;
}

export function calculateRsi(bars: readonly SpikeBar[], period = 14): Array<{ time: number; value: number }> {
  if (period < 1) throw new Error('period must be positive');
  if (bars.length <= period) return [];
  let gains = 0;
  let losses = 0;
  for (let index = 1; index <= period; index += 1) {
    const change = bars[index].close - bars[index - 1].close;
    gains += Math.max(change, 0);
    losses += Math.max(-change, 0);
  }
  let averageGain = gains / period;
  let averageLoss = losses / period;
  const result: Array<{ time: number; value: number }> = [];
  const value = () => (averageLoss === 0 ? 100 : 100 - 100 / (1 + averageGain / averageLoss));
  result.push({ time: bars[period].time, value: value() });
  for (let index = period + 1; index < bars.length; index += 1) {
    const change = bars[index].close - bars[index - 1].close;
    averageGain = (averageGain * (period - 1) + Math.max(change, 0)) / period;
    averageLoss = (averageLoss * (period - 1) + Math.max(-change, 0)) / period;
    result.push({ time: bars[index].time, value: value() });
  }
  return result;
}

export function reconcileBars(current: readonly SpikeBar[], updates: readonly SpikeBar[]): SpikeBar[] {
  const byTime = new Map<number, SpikeBar>(current.map((bar) => [bar.time, bar]));
  for (const update of updates) {
    const existing = byTime.get(update.time);
    if (!existing || update.ingestionRevision >= existing.ingestionRevision) byTime.set(update.time, update);
  }
  return [...byTime.values()].sort((left, right) => left.time - right.time);
}

export function missingFinalizedTimes(
  bars: readonly SpikeBar[],
  startTime: number,
  endTime: number,
  intervalSeconds: number,
): number[] {
  const finalized = new Set(bars.filter((bar) => bar.isFinal).map((bar) => bar.time));
  const missing: number[] = [];
  for (let time = startTime; time <= endTime; time += intervalSeconds) {
    if (!finalized.has(time)) missing.push(time);
  }
  return missing;
}

export function moveTrendPoint(drawing: TrendDrawing, endpoint: 'start' | 'end', point: DrawingPoint): TrendDrawing {
  return endpoint === 'start' ? { ...drawing, start: point } : { ...drawing, end: point };
}

export class SynchronizationGuard {
  private active = new Set<string>();

  run<T>(key: string, operation: () => T): T | undefined {
    if (this.active.has(key)) return undefined;
    this.active.add(key);
    try {
      return operation();
    } finally {
      this.active.delete(key);
    }
  }
}

export class SpikeLifecycleRegistry {
  charts = 0;
  listeners = 0;
  observers = 0;
  subscriptions = 0;

  assertClean(): void {
    if (this.charts || this.listeners || this.observers || this.subscriptions) {
      throw new Error(
        `spike lifecycle leak charts=${this.charts} listeners=${this.listeners} observers=${this.observers} subscriptions=${this.subscriptions}`,
      );
    }
  }
}
