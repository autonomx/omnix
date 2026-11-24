import { afterEach, describe, expect, it, vi } from 'vitest';
import type { JobRecord } from '../../api/client';
import { cancelOnStop, isStopped, sleepUnlessStopped, throwIfStopped } from './podcastControl';

const JOB = { id: 'job:1' } as JobRecord;

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

function cancelCalls(fetchMock: ReturnType<typeof vi.fn>): string[] {
  return fetchMock.mock.calls.map(([input]) => decodeURIComponent(new URL(String(input), 'http://localhost').pathname));
}

describe('podcast stop control', () => {
  it('cancels the job on the server when the run stops, and not once it is forgotten', async () => {
    const fetchMock = vi.fn(async () => Response.json({ id: 'job:1', status: 'cancel_requested' }));
    vi.stubGlobal('fetch', fetchMock);

    const forgotten = new AbortController();
    const forget = cancelOnStop(JOB, forgotten.signal);
    forget();
    forgotten.abort();
    expect(fetchMock).not.toHaveBeenCalled();

    const stop = new AbortController();
    cancelOnStop(JOB, stop.signal);
    stop.abort();
    await vi.waitFor(() => expect(cancelCalls(fetchMock)).toEqual(['/api/jobs/job:1/cancel']));

    cancelOnStop(JOB, stop.signal); // already stopped: cancels at once
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(cancelOnStop(JOB)).toBeTypeOf('function'); // no signal, nothing to cancel
  });

  it('throws a stop error only once stopped, and a stop cuts a wait short', async () => {
    vi.useFakeTimers();
    const stop = new AbortController();
    expect(() => throwIfStopped(stop.signal)).not.toThrow();
    const waited = vi.fn();
    void sleepUnlessStopped(60_000, stop.signal).then(waited);
    await vi.advanceTimersByTimeAsync(10);
    expect(waited).not.toHaveBeenCalled();
    stop.abort();
    await vi.advanceTimersByTimeAsync(0);
    expect(waited).toHaveBeenCalled();

    let error: unknown;
    try { throwIfStopped(stop.signal); } catch (caught) { error = caught; }
    expect(isStopped(error)).toBe(true);
    expect(isStopped(new Error('other'))).toBe(false);
  });
});
