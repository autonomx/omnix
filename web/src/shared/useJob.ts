import { useQuery } from '@tanstack/react-query';
import { omnixApiClient } from '../api/client';
import { isJobSettled, jobKeys } from '../api/jobs';

/**
 * One platform job, polled until it settles. A waiting, retrying or paused job has not finished,
 * so polling continues; a completed, failed, canceled or stale one stops it. An empty id is off.
 */
export function useJob(jobId: string | null | undefined, { intervalMs = 1000 }: { intervalMs?: number } = {}) {
  const id = jobId ?? '';
  return useQuery({
    queryKey: jobKeys.detail(id),
    queryFn: () => omnixApiClient.getJob(id),
    enabled: Boolean(id),
    refetchInterval: (query) => (isJobSettled(query.state.data?.status) ? false : intervalMs),
  });
}
