import { Button, Group, Progress, Text } from '@mantine/core';
import type { JobRecord } from '../../api/client';
import { OmnixStatusPill } from '../../design/primitives';
import { imageAssetUrl } from './ImageGenerationWorkspace';

const ACTIVE_STATUSES = new Set(['queued', 'waiting', 'retrying', 'leased', 'running', 'cancel_requested']);
const RETRYABLE_STATUSES = new Set(['failed', 'canceled', 'stale']);

interface ImageJobListProps {
  jobs: JobRecord[];
  cancelingJobId?: string;
  retryingJobId?: string;
  onCancel: (jobId: string) => void;
  onRetry: (jobId: string) => void;
}

export function ImageJobList({ jobs, cancelingJobId, retryingJobId, onCancel, onRetry }: ImageJobListProps) {
  if (!jobs.length) return <div className="platform-empty" role="status">No image jobs queued.</div>;

  return (
    <div className="feature-list">
      {jobs.map((job) => {
        const assetId = firstImageAssetId(job);
        const prompt = imageJobPrompt(job);
        return (
          <article className="feature-mini-card" key={job.id} aria-label={`Image job ${job.id}`}>
            <Group justify="space-between" align="start">
              <div>
                <strong>{prompt || job.type}</strong>
                <Text size="xs">{new Date(job.created_at).toLocaleString()}</Text>
              </div>
              <OmnixStatusPill>{job.status}</OmnixStatusPill>
            </Group>
            <Progress value={progressPercent(job.progress)} aria-label={`${job.type} progress`} />
            {job.progress?.message ? <Text size="sm">{job.progress.message}</Text> : null}
            {job.error ? <Text c="red" size="sm" role="alert">{job.error.message} ({job.error.code})</Text> : null}
            <Group gap="xs">
              {assetId ? (
                <>
                  <Button component="a" href={imageAssetUrl(assetId)} target="_blank" rel="noreferrer" size="xs" variant="light">Open result</Button>
                  <Button component="a" href={imageAssetUrl(assetId, true)} download size="xs" variant="default">Download</Button>
                </>
              ) : null}
              {canCancelImageJob(job) ? (
                <Button color="red" disabled={cancelingJobId === job.id || job.status === 'cancel_requested'} loading={cancelingJobId === job.id} onClick={() => onCancel(job.id)} size="xs" variant="subtle">Cancel</Button>
              ) : null}
              {canRetryImageJob(job) ? (
                <Button disabled={retryingJobId === job.id} loading={retryingJobId === job.id} onClick={() => onRetry(job.id)} size="xs" variant="light">Retry</Button>
              ) : null}
            </Group>
          </article>
        );
      })}
    </div>
  );
}

export function canCancelImageJob(job: JobRecord): boolean {
  return ACTIVE_STATUSES.has(job.status);
}

export function canRetryImageJob(job: JobRecord): boolean {
  return RETRYABLE_STATUSES.has(job.status);
}

export function firstImageAssetId(job: JobRecord): string | undefined {
  for (const ref of job.output_refs ?? []) {
    if (ref.type === 'image' && typeof ref.asset_id === 'string' && ref.asset_id) return ref.asset_id;
  }
  return undefined;
}

function imageJobPrompt(job: JobRecord): string {
  const prompt = job.input_payload?.prompt;
  return typeof prompt === 'string' ? prompt : '';
}

function progressPercent(progress: { current: number; total: number } | undefined): number {
  if (!progress || progress.total <= 0) return 0;
  return Math.min(100, Math.round((progress.current / progress.total) * 100));
}
