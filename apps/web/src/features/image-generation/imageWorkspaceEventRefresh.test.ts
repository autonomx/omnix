import { afterEach, describe, expect, it, vi } from 'vitest';
import { createImageEventRefreshScheduler } from './imageWorkspaceModel';

afterEach(() => {
  vi.useRealTimers();
});

describe('image event refresh scheduler', () => {
  it('coalesces event bursts and preserves an asset refresh request', () => {
    vi.useFakeTimers();
    const flush = vi.fn();
    const scheduler = createImageEventRefreshScheduler(flush, 750);

    for (let index = 0; index < 100; index += 1) scheduler.schedule(false);
    scheduler.schedule(true);

    expect(flush).not.toHaveBeenCalled();
    vi.advanceTimersByTime(749);
    expect(flush).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(flush).toHaveBeenCalledTimes(1);
    expect(flush).toHaveBeenCalledWith(true);
  });

  it('cancels a pending refresh when disposed', () => {
    vi.useFakeTimers();
    const flush = vi.fn();
    const scheduler = createImageEventRefreshScheduler(flush, 750);

    scheduler.schedule();
    scheduler.dispose();
    vi.runAllTimers();

    expect(flush).not.toHaveBeenCalled();
  });
});
