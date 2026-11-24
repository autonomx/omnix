import { omnixApiClient, type JobRecord } from '../../api/client';
import { jobKeys } from '../../api/jobs';
import { jobOutputRefs } from '../../api/schemas/streams';
import type { ScriptSegment } from './podcastScript';
import type { TranscriptRow } from './PodcastStudioParts';
import { timelineFrom, type LineStart } from './podcastTimeline';

/**
 * The podcast library (owner request 2026-11-24): every finished podcast, newest first. An episode is a completed
 * final render (a podcast `tts.multi_speaker_synthesize` job); its audio is the stored asset the job points at, so
 * the library lists what the server keeps rather than what this browser saw.
 */
export type PodcastEpisode = {
  jobId: string;
  assetId: string;
  title: string;
  createdAt: string;
  durationSeconds: number;
  format: string;
  speakers: string[];
  audioUrl: string;
};

export const FINAL_RENDER_TYPE = 'tts.multi_speaker_synthesize';
// Under the jobs key, so a finished run's job refresh also refreshes the library.
export const podcastLibraryKey = [...jobKeys.all, 'podcast-library'] as const;
const PAGE_SIZE = 100;
const MAX_PAGES = 20;

const text = (value: unknown) => (typeof value === 'string' ? value.trim() : '');

export function episodeFrom(job: JobRecord): PodcastEpisode | null {
  if (job.module !== 'podcast' || job.type !== FINAL_RENDER_TYPE || job.status !== 'completed') return null;
  const ref = jobOutputRefs(job).find((entry) => text(entry.audio_url).startsWith('/api/') || text(entry.data_url).startsWith('data:audio/'));
  if (!ref) return null;
  const payload = (job.input_payload ?? {}) as Record<string, unknown>;
  const speakers = Array.isArray(payload.script_speakers)
    ? payload.script_speakers.map((entry) => text((entry as { name?: unknown } | null)?.name)).filter(Boolean)
    : [];
  return {
    jobId: job.id,
    assetId: text(ref.asset_id),
    title: text(payload.title) || text(ref.title) || 'Untitled episode',
    createdAt: job.created_at,
    durationSeconds: Number(ref.duration) || 0,
    format: text(payload.format),
    speakers,
    audioUrl: text(ref.audio_url) || text(ref.data_url),
  };
}

/** Every finished podcast on the server, newest first. */
export async function listPodcastEpisodes(): Promise<PodcastEpisode[]> {
  const episodes: PodcastEpisode[] = [];
  let cursor: string | null = null;
  for (let page = 0; page < MAX_PAGES; page += 1) {
    const response = await omnixApiClient.listJobs({ module: 'podcast', type: FINAL_RENDER_TYPE, status: 'completed', limit: PAGE_SIZE, cursor });
    for (const job of response.jobs) {
      const episode = episodeFrom(job);
      if (episode) episodes.push(episode);
    }
    if (!response.has_more || !response.next_cursor) break;
    cursor = response.next_cursor;
  }
  return episodes;
}

export const clock = (seconds: number) => `${String(Math.floor((seconds || 0) / 60)).padStart(2, '0')}:${String(Math.floor(seconds || 0) % 60).padStart(2, '0')}`;

/** Transcript rows for a script, its lines spread evenly over `total` seconds. */
export const transcriptRows = (segments: Array<Pick<ScriptSegment, 'speaker' | 'text'>>, total: number): TranscriptRow[] => segments.map((segment, index) => ({
  timestamp: clock(index * Math.max(8, total / Math.max(1, segments.length))),
  speaker: segment.speaker,
  text: segment.text,
}));

/** The episode's script as transcript rows; job lists trim long fields, so this reads the whole job. */
export async function episodeTranscript(episode: PodcastEpisode): Promise<{ rows: TranscriptRow[]; timeline: LineStart[] }> {
  const job = await omnixApiClient.getJob(episode.jobId);
  const segments = (job.input_payload as { script_segments?: unknown } | undefined)?.script_segments;
  // Where each line plays, when the render reported it (renders since 2026-11-24): the transcript follows the audio.
  const timeline = timelineFrom(jobOutputRefs(job).find((ref) => ref.asset_id === episode.assetId)?.timeline);
  if (!Array.isArray(segments)) return { rows: [], timeline };
  // The render skips lines without words, as here, so a line's position matches its place in the timeline.
  const lines = segments
    .map((entry) => ({ speaker: text((entry as { speaker?: unknown })?.speaker) || 'Speaker', text: text((entry as { text?: unknown })?.text) }))
    .filter((line) => line.text);
  const starts = new Map(timeline.map((entry) => [entry.line, entry.start]));
  const rows = transcriptRows(lines, episode.durationSeconds)
    .map((row, position) => (starts.has(position) ? { ...row, timestamp: clock(starts.get(position) ?? 0) } : row));
  return { rows, timeline };
}
