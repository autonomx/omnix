import { useState } from 'react';
import type { JobRecord } from '../../api/client';
import { useNow } from '../../shared/timers';

const TICK_MS = 250;
/** Within a step the bar eases toward, but never past, this share of it; only the job moves it on. */
const STEP_CEILING = 0.9;
const MIN_STEP_SECONDS = 2;

/**
 * How far a speech render is. The job reports each finished line and the assembly; between
 * reports the bar eases toward the next one, paced by how long earlier lines took (or, before
 * any has finished, by the script's estimated length), so it moves without claiming a line is done.
 */
export function RenderProgress({ job, estimatedSeconds }: { job: JobRecord | undefined; estimatedSeconds: number }) {
  const status = job?.status ?? 'queued';
  const running = status === 'running';
  const total = Math.max(1, job?.progress?.total ?? 1);
  const current = Math.min(total, Math.max(0, job?.progress?.current ?? 0));
  // The clock keeps time while waiting too, so a line's pace starts when the job starts.
  const finishedJob = status === 'completed' || status === 'failed' || status === 'canceled';
  const now = useNow(TICK_MS, !finishedJob).getTime();
  // The step the job last reported, when it was first seen, and how long each finished line took.
  const [step, setStep] = useState({ current: -1, startedAt: now, durations: [] as number[] });

  if (running && step.current !== current) {
    const finished = step.current >= 0 && current > step.current
      ? [...step.durations, (now - step.startedAt) / 1000 / (current - step.current)]
      : step.durations;
    setStep({ current, startedAt: now, durations: finished });
  }

  let percent = 0;
  if (status === 'completed') {
    percent = 100;
  } else if (running) {
    const { durations, startedAt } = step;
    const lines = Math.max(1, total - 1);
    const pace = durations.length
      ? durations.reduce((sum, value) => sum + value, 0) / durations.length
      : estimatedSeconds / lines;
    const elapsed = Math.max(0, (now - startedAt) / 1000);
    const within = STEP_CEILING * (1 - Math.exp(-elapsed / Math.max(MIN_STEP_SECONDS, pace)));
    percent = Math.min(99, Math.floor(((current + within) / total) * 100));
  }

  const label = status === 'completed'
    ? 'Done'
    : running
      ? `${job?.progress?.message || 'Generating speech'}…`
      : 'Waiting for the speech engine…';

  return (
    <div className="voice-render-progress" role="status" aria-live="polite">
      <div className="voice-render-progress-head">
        <span>{label}</span>
        <b>{percent}%</b>
      </div>
      <div className="voice-render-progress-track" role="progressbar" aria-label="Speech generation progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent}>
        <span style={{ width: `${percent}%` }} />
      </div>
    </div>
  );
}
