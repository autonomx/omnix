import { describe, expect, it } from 'vitest';
import {
  SpikeLifecycleRegistry,
  SynchronizationGuard,
  calculateRsi,
  generateSpikeBars,
  missingFinalizedTimes,
  moveTrendPoint,
  reconcileBars,
} from './tradingSpikeCore';

describe('trading chart feasibility core', () => {
  it('generates deterministic ordered 5,000-bar datasets', () => {
    const first = generateSpikeBars();
    const second = generateSpikeBars();
    expect(first).toEqual(second);
    expect(first).toHaveLength(5_000);
    expect(first[0].time).toBeLessThan(first.at(-1)!.time);
  });

  it('calculates bounded RSI output after warmup', () => {
    const result = calculateRsi(generateSpikeBars(200));
    expect(result).toHaveLength(186);
    expect(result.every((point) => point.value >= 0 && point.value <= 100)).toBe(true);
  });

  it('reconciles duplicates, corrections, partial bars, and revisions', () => {
    const base = generateSpikeBars(4);
    const corrected = { ...base[2], close: base[2].close + 20, ingestionRevision: 2 };
    const stale = { ...base[2], close: 1, ingestionRevision: 1 };
    const partial = { ...base[3], close: base[3].close + 5, isFinal: false, ingestionRevision: 2 };
    const result = reconcileBars(base, [stale, corrected, partial]);
    expect(result).toHaveLength(4);
    expect(result[2].close).toBe(corrected.close);
    expect(result[3].isFinal).toBe(false);
  });

  it('identifies exact finalized gaps', () => {
    const bars = generateSpikeBars(5);
    const missing = bars.filter((_, index) => index !== 2);
    expect(missingFinalizedTimes(missing, bars[0].time, bars[4].time, 60)).toEqual([bars[2].time]);
  });

  it('keeps drawing coordinates independent from pixels', () => {
    const drawing = {
      id: 'trend',
      start: { time: 100, price: 10 },
      end: { time: 200, price: 20 },
    };
    expect(moveTrendPoint(drawing, 'end', { time: 250, price: 25 })).toEqual({
      ...drawing,
      end: { time: 250, price: 25 },
    });
  });

  it('prevents synchronization feedback loops and releases the guard', () => {
    const guard = new SynchronizationGuard();
    let calls = 0;
    guard.run('crosshair', () => {
      calls += 1;
      guard.run('crosshair', () => {
        calls += 1;
      });
    });
    guard.run('crosshair', () => {
      calls += 1;
    });
    expect(calls).toBe(2);
  });

  it('fails closed when lifecycle resources remain registered', () => {
    const lifecycle = new SpikeLifecycleRegistry();
    lifecycle.assertClean();
    lifecycle.listeners = 1;
    expect(() => lifecycle.assertClean()).toThrow(/lifecycle leak/);
  });
});
