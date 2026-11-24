import { omnixApiClient, type JobRecord } from '../../api/client';

/**
 * The producer's Stop for a podcast run (owner request 2026-11-24): one AbortSignal reaches the script job, each
 * preview line and the final render. Stopping cancels the job in flight and nothing after it is started.
 */
export const STOPPED_MESSAGE = 'Podcast stopped.';

export function stoppedError(): Error {
  const error = new Error(STOPPED_MESSAGE);
  error.name = 'AbortError';
  return error;
}

export function isStopped(error: unknown): boolean {
  return error instanceof Error && error.name === 'AbortError';
}

export function throwIfStopped(signal?: AbortSignal): void {
  if (signal?.aborted) throw stoppedError();
}

/** Cancels `job` on the server once `signal` aborts; call the returned function when the job no longer matters. */
export function cancelOnStop(job: JobRecord, signal?: AbortSignal): () => void {
  if (!signal) return () => undefined;
  const cancel = () => { void omnixApiClient.cancelJob(job.id, 'Stopped by the producer.').catch(() => undefined); };
  if (signal.aborted) {
    cancel();
    return () => undefined;
  }
  signal.addEventListener('abort', cancel, { once: true });
  return () => signal.removeEventListener('abort', cancel);
}

/** Waits `ms`, or less when `signal` aborts first (a stopped run does not sit out a poll). */
export function sleepUnlessStopped(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    if (signal?.aborted) return resolve();
    const done = () => {
      window.clearTimeout(timer);
      signal?.removeEventListener('abort', done);
      resolve();
    };
    const timer = window.setTimeout(done, ms);
    signal?.addEventListener('abort', done, { once: true });
  });
}
