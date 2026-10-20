import type { JobRecord } from '../../api/client';
import { isFallbackOutputRef, jobOutputRefs, type JobOutputRef } from '../../api/schemas/streams';

/** A finished take the transport can play. */
export interface PlayableVoiceOutput {
  /** The stored take (WAV), when the job saved one; exports and peaks need it. */
  assetId: string;
  dataUrl: string;
  duration: number;
  jobId: string;
  key: string;
  title: string;
}

export function activeJobs<T extends { status: string }>(jobs: T[]): T[] {
  return jobs.filter((job) => job.status === 'queued' || job.status === 'running' || job.status === 'leased');
}

export function mergeVoiceJobs(jobs: Array<JobRecord | undefined>): JobRecord[] {
  const merged = new Map<string, JobRecord>();
  for (const job of jobs) {
    if (job?.id) {
      merged.set(job.id, job);
    }
  }
  return Array.from(merged.values());
}

// New outputs reference the stored asset (audio_url); older job rows embed
// the audio as a data URL.
function playableAudioUrl(ref: JobOutputRef): string {
  if (typeof ref.audio_url === 'string' && ref.audio_url.startsWith('/api/assets/')) return ref.audio_url;
  if (typeof ref.data_url === 'string' && ref.data_url.startsWith('data:audio/')) return ref.data_url;
  return '';
}

function isPlayableAudioRef(ref: JobOutputRef): boolean {
  return playableAudioUrl(ref) !== '' && !isFallbackOutputRef(ref);
}

export function extractPlayableOutputs(jobs: JobRecord[]): PlayableVoiceOutput[] {
  const outputs: PlayableVoiceOutput[] = [];
  for (const job of jobs) {
    for (const ref of jobOutputRefs(job)) {
      if (isPlayableAudioRef(ref)) {
        const title = ref.title || job.type || 'voice_output';
        outputs.push({
          assetId: typeof ref.asset_id === 'string' ? ref.asset_id : '',
          dataUrl: playableAudioUrl(ref),
          duration: Number(ref.duration || 0),
          jobId: job.id,
          key: `${job.id}:${ref.asset_id || ref.title || outputs.length}`,
          title,
        });
      }
    }
  }
  return outputs;
}

export function transcriptFromJob(job: JobRecord): string {
  const transcript = jobOutputRefs(job).find((ref) => ref.type === 'transcript' && typeof ref.content === 'string')?.content;
  return typeof transcript === 'string' ? transcript.trim() : '';
}

export function voiceJobErrorMessage(job: JobRecord | undefined): string {
  if (!job || job.status !== 'failed') {
    return '';
  }
  const message = typeof job.error?.message === 'string' ? job.error.message : 'Voice Studio job failed.';
  return `Voice Studio failed: ${message}`;
}

/** Warnings the clone job's sample check reported, if any. */
export function sampleCheckWarnings(job: JobRecord | undefined): string[] {
  if (!job) return [];
  for (const ref of jobOutputRefs(job)) {
    const check = (ref as { sample_check?: unknown }).sample_check;
    if (check && typeof check === 'object' && Array.isArray((check as { warnings?: unknown }).warnings)) {
      return ((check as { warnings: unknown[] }).warnings).filter((item): item is string => typeof item === 'string');
    }
  }
  return [];
}
