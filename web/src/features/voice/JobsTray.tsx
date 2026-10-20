import { Button } from '@mantine/core';
import { useState } from 'react';
import type { JobRecord } from '../../api/client';
import { jobProgressPercent } from '../../api/jobProgress';
import { OmnixStatusPill } from '../../design/primitives';
import { activeJobs } from './voiceOutputs';

type JobQueueFilter = 'active' | 'recent' | 'failed';

/** Active, recent and failed Voice Studio jobs; active ones can be cancelled. */
export function JobsTray({ jobs, playableJobIds, selectedJobId, onSelect, onCancel, cancelling, onRetry, retrying = '' }: {
  jobs: JobRecord[];
  playableJobIds: ReadonlySet<string>;
  selectedJobId: string;
  onSelect: (jobId: string) => void;
  onCancel: (jobId: string) => void;
  cancelling: string;
  /** Queue a fresh copy of a failed or cancelled job. */
  onRetry?: (jobId: string) => void;
  retrying?: string;
}) {
  const [filter, setFilter] = useState<JobQueueFilter>('active');
  const [open, setOpen] = useState(true);
  const active = activeJobs(jobs);
  const failed = jobs.filter((job) => job.status === 'failed');
  const recent = jobs.filter((job) => !active.includes(job));
  const shown = filter === 'active' ? active : filter === 'failed' ? failed : recent;
  return (
    <section className="voice-jobs-tray" aria-label="Jobs">
      <div className="voice-jobs-head">
        <button type="button" className="voice-jobs-toggle" aria-expanded={open} onClick={() => setOpen((value) => !value)}>Jobs</button>
        <div className="queue-tabs">
          <button className={filter === 'active' ? 'active' : ''} type="button" aria-pressed={filter === 'active'} onClick={() => setFilter('active')}>Active ({active.length})</button>
          <button className={filter === 'recent' ? 'active' : ''} type="button" aria-pressed={filter === 'recent'} onClick={() => setFilter('recent')}>Recent ({recent.length})</button>
          <button className={filter === 'failed' ? 'active' : ''} type="button" aria-pressed={filter === 'failed'} onClick={() => setFilter('failed')}>Failed ({failed.length})</button>
        </div>
      </div>
      {open ? (
        <div className="queue-list-final">
          {shown.length ? shown.slice(0, 8).map((job) => {
            const progress = jobProgressPercent(job.progress);
            const isActive = active.includes(job);
            return (
              <article className={job.id === selectedJobId ? 'queue-row-final selected' : 'queue-row-final'} key={job.id}>
                <span className="job-icon" aria-hidden="true">▥</span>
                <div><b>{job.type}</b><small>{job.status === 'failed' && typeof job.error?.message === 'string' ? job.error.message : job.module}</small></div>
                <div><OmnixStatusPill>{job.status}</OmnixStatusPill>{progress ? <div className="queue-progress"><span style={{ width: `${progress}%` }} /></div> : null}</div>
                <small>{progress || job.status === 'completed' ? `${progress}%` : '—'}</small>
                {isActive ? (
                  <Button size="compact-xs" variant="subtle" color="red" loading={cancelling === job.id} onClick={() => onCancel(job.id)}>Cancel</Button>
                ) : (job.status === 'failed' || job.status === 'canceled') && onRetry ? (
                  <Button size="compact-xs" variant="subtle" loading={retrying === job.id} onClick={() => onRetry(job.id)}>Retry</Button>
                ) : (
                  <button type="button" aria-label={`Play ${job.type}`} disabled={!playableJobIds.has(job.id)} onClick={() => onSelect(job.id)}>▶</button>
                )}
              </article>
            );
          }) : <div className="platform-empty" role="status">{filter === 'active' ? 'No jobs are running.' : filter === 'failed' ? 'No failed jobs.' : 'No finished jobs yet.'}</div>}
        </div>
      ) : null}
    </section>
  );
}
