import type { components } from './generated/core';

/** A platform job's status, as the gateway reports it. */
export type JobStatus = components['schemas']['JobStatus'];

/** A job in one of these states has finished: its result will not change. */
export const SETTLED_JOB_STATUSES: ReadonlySet<string> = new Set<JobStatus>(['completed', 'failed', 'canceled', 'stale']);

/**
 * A job in one of these states is still moving toward a result. A waiting or retrying job has not
 * finished: its result can still arrive. A paused job is neither active nor settled.
 */
export const ACTIVE_JOB_STATUSES: ReadonlySet<string> = new Set<JobStatus>([
  'queued',
  'leased',
  'running',
  'waiting',
  'retrying',
  'cancel_requested',
]);

/**
 * Query keys for platform jobs. Invalidating `all` refreshes every job list and every single job;
 * a single job lives under `detail`, so its id cannot collide with a list's name.
 */
export const jobKeys = {
  all: ['platform', 'jobs'] as const,
  detail: (jobId: string) => ['platform', 'jobs', 'detail', jobId] as const,
};

export function isJobSettled(status: string | null | undefined): boolean {
  return SETTLED_JOB_STATUSES.has(status ?? '');
}

export function isJobActive(status: string | null | undefined): boolean {
  return ACTIVE_JOB_STATUSES.has(status ?? '');
}
