import { describe, expect, it } from 'vitest';
import { isJobActive, isJobSettled, type JobStatus } from './jobs';

describe('job status', () => {
  it('keeps a waiting or retrying job active, so its result is still polled for', () => {
    for (const status of ['queued', 'leased', 'running', 'waiting', 'retrying', 'cancel_requested'] as JobStatus[]) {
      expect(isJobActive(status)).toBe(true);
      expect(isJobSettled(status)).toBe(false);
    }
  });

  it('settles a completed, failed, canceled or stale job', () => {
    for (const status of ['completed', 'failed', 'canceled', 'stale'] as JobStatus[]) {
      expect(isJobSettled(status)).toBe(true);
      expect(isJobActive(status)).toBe(false);
    }
  });

  it('treats a paused job as neither active nor settled, and a missing status as neither', () => {
    expect(isJobActive('paused')).toBe(false);
    expect(isJobSettled('paused')).toBe(false);
    expect(isJobActive(undefined)).toBe(false);
    expect(isJobSettled(null)).toBe(false);
  });
});
