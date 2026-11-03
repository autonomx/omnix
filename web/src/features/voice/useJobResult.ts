import { useQuery } from '@tanstack/react-query';
import { omnixApiClient, type JobRecord } from '../../api/client';

// A job that is waiting or retrying has not finished: its result can still arrive.
const SETTLED = new Set(['completed', 'failed', 'canceled', 'stale']);

/** A job polled every second until it settles. */
export function useJobResult(jobId: string) {
  return useQuery({
    queryKey: ['platform', 'jobs', jobId],
    queryFn: () => omnixApiClient.getJob(jobId),
    enabled: Boolean(jobId),
    refetchInterval: (query) => (jobSettled(query.state.data) ? false : 1000),
  });
}

export function jobSettled(job: JobRecord | undefined): boolean {
  return SETTLED.has(job?.status ?? '');
}

/** The first output reference of a finished job. */
export function firstOutput(job: JobRecord | undefined): Record<string, unknown> | undefined {
  const refs = (job?.output_refs ?? []) as unknown as Array<Record<string, unknown>>;
  return refs[0];
}
