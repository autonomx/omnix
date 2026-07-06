import { Button, Progress, Text } from '@mantine/core';
import { useState } from 'react';
import type { JobRecord } from '../../api/client';
import { OmnixStatusPill } from '../../design/primitives';
import { imageAssetUrl } from './imageWorkspaceModel';

const ACTIVE_STATUSES = new Set(['queued', 'waiting', 'retrying', 'leased', 'running', 'cancel_requested']);
const RETRYABLE_STATUSES = new Set(['failed', 'canceled', 'stale']);
const COLLAPSED_JOB_LIMIT = 4;

interface ImageJobListProps {
  jobs: JobRecord[];
  cancelingJobId?: string;
  retryingJobId?: string;
  onCancel: (jobId: string) => void;
  onRetry: (jobId: string) => void;
  onSelectAsset?: (assetId: string) => void;
}

export function ImageJobList({ jobs, cancelingJobId, retryingJobId, onCancel, onRetry, onSelectAsset }: ImageJobListProps) {
  const [showAll, setShowAll] = useState(false);
  if (!jobs.length) return <div className="image-empty-state" role="status">No image jobs queued.</div>;

  const visibleJobs = showAll ? jobs : jobs.slice(0, COLLAPSED_JOB_LIMIT);
  const hasHiddenJobs = jobs.length > COLLAPSED_JOB_LIMIT;

  return (
    <div className="image-job-list-wrap">
      <div className="image-job-list">
        {visibleJobs.map((job) => {
          const assetId = firstImageAssetId(job);
          const prompt = imageJobPrompt(job);
          const progress = progressPercent(job.progress);
          return (
            <article className="image-job-card" key={job.id} aria-label={`Image job ${prompt || job.id}`}>
              <div className="image-job-header">
                <div>
                  <strong title={prompt || job.type}>{prompt || job.type}</strong>
                  <time>{new Date(job.created_at).toLocaleString()}</time>
                </div>
                <OmnixStatusPill>{job.status}</OmnixStatusPill>
              </div>

              <div className="image-job-content">
                {assetId ? <img alt="" loading="lazy" src={imageAssetUrl(assetId)} /> : <span className="image-job-placeholder" aria-hidden="true">✦</span>}
                <div className="image-job-details">
                  <Progress value={progress} aria-label={`${job.type} progress`} />
                  <Text size="xs">{job.progress?.message || jobStatusMessage(job.status, progress)}</Text>
                  {job.error ? <Text c="red" size="xs" role="alert">{job.error.message} ({job.error.code})</Text> : null}
                  <div className="image-job-actions">
                    {assetId ? (
                      <>
                        {onSelectAsset ? (
                          <Button size="compact-xs" variant="light" onClick={() => onSelectAsset(assetId)}>View in Latest Result</Button>
                        ) : (
                          <Button component="a" href={imageAssetUrl(assetId)} size="compact-xs" variant="light">Open result</Button>
                        )}
                        <Button component="a" href={imageAssetUrl(assetId, true)} download size="compact-xs" variant="subtle" aria-label="Download image result">↓</Button>
                      </>
                    ) : null}
                    {canCancelImageJob(job) ? (
                      <Button color="red" disabled={cancelingJobId === job.id || job.status === 'cancel_requested'} loading={cancelingJobId === job.id} onClick={() => onCancel(job.id)} size="compact-xs" variant="subtle">Cancel</Button>
                    ) : null}
                    {canRetryImageJob(job) ? (
                      <Button disabled={retryingJobId === job.id} loading={retryingJobId === job.id} onClick={() => onRetry(job.id)} size="compact-xs" variant="light">Retry</Button>
                    ) : null}
                  </div>
                </div>
              </div>
            </article>
          );
        })}
      </div>
      <footer className="image-job-footer">
        <span>{visibleJobs.length} of {jobs.length} job{jobs.length === 1 ? '' : 's'}</span>
        {hasHiddenJobs ? (
          <button type="button" onClick={() => setShowAll((value) => !value)}>{showAll ? 'Show latest only' : `Show all ${jobs.length}`}</button>
        ) : null}
      </footer>
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

function jobStatusMessage(status: string, progress: number): string {
  if (status === 'completed') return 'Completed successfully';
  if (status === 'failed') return 'Generation failed';
  if (status === 'canceled') return 'Canceled';
  if (status === 'running') return `Generating · ${progress}%`;
  if (status === 'leased') return 'Preparing provider';
  return 'Waiting in queue';
}
