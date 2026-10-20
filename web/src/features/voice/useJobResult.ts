import { useQuery } from '@tanstack/react-query';
import { omnixApiClient, type JobRecord } from '../../api/client';

const ACTIVE = new Set(['', 'queued', 'leased', 'running']);

/** A job polled every second until it settles. */
export function useJobResult(jobId: string) {
  return useQuery({
    queryKey: ['platform', 'jobs', jobId],
    queryFn: () => omnixApiClient.getJob(jobId),
    enabled: Boolean(jobId),
    refetchInterval: (query) => (ACTIVE.has(query.state.data?.status ?? '') ? 1000 : false),
  });
}

export function jobSettled(job: JobRecord | undefined): boolean {
  return Boolean(job) && !ACTIVE.has(job?.status ?? '');
}

/** The first output reference of a finished job. */
export function firstOutput(job: JobRecord | undefined): Record<string, unknown> | undefined {
  const refs = (job?.output_refs ?? []) as unknown as Array<Record<string, unknown>>;
  return refs[0];
}
