import { omnixApiClient, type JobRecord } from '../../api/client';
import { jobOutputRefs } from '../../api/schemas/streams';
import { loadSettingsProfile, podcastDefaults } from '../settings';
import { cancelOnStop, sleepUnlessStopped, throwIfStopped } from './podcastControl';

// `pause_before_ms` is the script's pacing (a quick reaction comes in sooner); `delivery_instruction` is how the
// line is said, which only engines that take delivery notes (Fish S2 Pro) hear.
export type ScriptSegment = {
  index: number;
  speaker: string;
  text: string;
  pause_before_ms?: number;
  delivery_instruction?: string;
};
// What the script job measured (`script_quality` in `podcast_script.py`).
export type ScriptQuality = {
  lines?: number;
  words?: number;
  minutes?: number;
  target_minutes?: number;
  near_repeats?: number;
  long_lines?: number;
  speaker_share?: Record<string, number>;
  parts?: number;
  flagged?: number;
  edited?: number;
  cut?: number;
};
export type PodcastScript = { segments: ScriptSegment[]; model: string; quality: ScriptQuality | null };
export type ScriptSpeaker = {
  name: string;
  role?: string;
  identity?: string;
  beliefs?: string;
  personality?: string;
  speakingStyle?: string;
  goal?: string;
  instructions?: string;
};
export type ScriptRequest = {
  title: string;
  brief: string;
  audience: string;
  format: string;
  tone: string;
  durationMinutes: number;
  speakers: ScriptSpeaker[];
  // The producer's notes for the script to draw its facts from.
  sources?: string;
};

// The script job's own timeout (`podcast.generate`, 1800 s: a plan and up to eight parts), plus time queued behind
// other model work.
const SCRIPT_WAIT_MS = 31 * 60 * 1000;
const POLL_MS = 1500;
const SETTLED = new Set(['completed', 'failed', 'canceled', 'cancelled', 'stale']);

/**
 * The episode's script, written by the podcast's model in a `podcast.generate` job (owner report 2026-11-24: the
 * old chat-message path never got a reply, so every episode fell back to six template lines on repeat). A script
 * that cannot be had or read is an error the producer sees, never a stand-in.
 */
export async function requestPodcastScript(
  request: ScriptRequest,
  options: { waitMs?: number; pollMs?: number; onProgress?: (message: string, progress?: JobRecord['progress']) => void; signal?: AbortSignal } = {},
): Promise<PodcastScript> {
  const { signal } = options;
  const route = await scriptRoute();
  throwIfStopped(signal);
  const names = request.speakers.map((speaker) => speaker.name.trim()).filter(Boolean);
  const job = await omnixApiClient.createJob({
    module: 'podcast',
    type: 'podcast.generate',
    resource_class: 'gpu:llm',
    priority: 1,
    input_payload: {
      title: request.title,
      brief: request.brief,
      audience: request.audience,
      format: request.format,
      tone: request.tone,
      duration_minutes: request.durationMinutes,
      ...(request.sources?.trim() ? { sources: request.sources.trim() } : {}),
      speakers: names,
      speaker_profiles: request.speakers.map((speaker) => ({
        name: speaker.name.trim(),
        role: speaker.role,
        identity: speaker.identity,
        beliefs: speaker.beliefs,
        personality: speaker.personality,
        speaking_style: speaker.speakingStyle,
        goal: speaker.goal,
        instructions: speaker.instructions,
      })),
      ...route,
    },
  });
  // Stop cancels the script job: its writer checks between model replies (story/podcast_script.py).
  const forget = cancelOnStop(job, signal);
  const settled = await settledJob(job, options.waitMs ?? SCRIPT_WAIT_MS, options.pollMs ?? POLL_MS, options.onProgress, signal)
    .finally(forget);
  throwIfStopped(signal);
  const status = String(settled.status || '').toLowerCase();
  if (status !== 'completed') {
    if (!SETTLED.has(status)) throw new Error('The podcast script is still being written. It took longer than expected; try again shortly.');
    const reason = settled.error?.message || settled.error?.code || status;
    throw new Error(`The podcast script could not be written: ${reason}`);
  }
  const ref = jobOutputRefs(settled).find((item) => item.type === 'podcast_script');
  const content = ref?.content;
  const segments = parseScriptSegments(typeof content === 'string' ? content : '', names);
  if (!segments.length) throw new Error('The model returned a podcast script without speaker lines. Try again, or pick another podcast model in Settings.');
  const quality = ref?.script_quality;
  return {
    segments,
    model: String(ref?.resolved_model || ref?.model_id || '').trim(),
    quality: quality && typeof quality === 'object' ? (quality as ScriptQuality) : null,
  };
}

// What the script came to, for the director note: " (1,480 words, about 10 of 10 minutes; 2 repeated lines
// rewritten; Host 52%, Guest 48%; written by qwen3)".
export function scriptSummary(quality: ScriptQuality | null, model: string) {
  const parts: string[] = [];
  if (quality?.words) {
    const length = `${quality.words.toLocaleString('en-US')} words`;
    parts.push(quality.target_minutes ? `${length}, about ${Math.round(quality.minutes ?? 0)} of ${quality.target_minutes} minutes` : length);
  }
  const fixed = (quality?.edited ?? 0) + (quality?.cut ?? 0);
  if (fixed) parts.push(`${fixed} repeated or overlong line${fixed === 1 ? '' : 's'} fixed`);
  if (quality?.near_repeats) parts.push(`${quality.near_repeats} near-repeat${quality.near_repeats === 1 ? '' : 's'} left`);
  const shares = Object.entries(quality?.speaker_share ?? {});
  if (shares.length > 1) parts.push(shares.map(([name, share]) => `${name} ${share}%`).join(', '));
  if (model) parts.push(`written by ${model}`);
  return parts.length ? ` (${parts.join('; ')})` : '';
}

async function scriptRoute(): Promise<{ provider_id?: string; model_id?: string }> {
  try {
    const { profile } = await loadSettingsProfile();
    const defaults = podcastDefaults(profile);
    return { provider_id: defaults.providerId || undefined, model_id: defaults.modelId || undefined };
  } catch {
    return {};
  }
}

// A long episode is written in parts; the job's progress says which one ("Writing part 2 of 6").
async function settledJob(job: JobRecord, waitMs: number, pollMs: number, onProgress?: (message: string, progress?: JobRecord['progress']) => void, signal?: AbortSignal) {
  let latest = job;
  let shown = '';
  const started = Date.now();
  while (!SETTLED.has(String(latest.status || '').toLowerCase()) && Date.now() - started < waitMs) {
    await sleepUnlessStopped(pollMs, signal);
    throwIfStopped(signal);
    try { latest = await omnixApiClient.getJob(job.id); } catch {}
    const message = String(latest.progress?.message || '').trim();
    if (message && message !== shown && !SETTLED.has(String(latest.status || '').toLowerCase())) {
      shown = message;
      onProgress?.(message, latest.progress);
    }
  }
  return latest;
}

/**
 * Speaker lines from a model's script: JSON (`{"segments": [...]}` or a bare list, fenced or not), the complete
 * `{"speaker", "text"}` objects of JSON cut off mid-way, or else `Name: line` rows for the cast's names. Speakers are
 * matched to the cast case-insensitively, and a line said word for word earlier is dropped.
 */
export function parseScriptSegments(text: string, names: string[]): ScriptSegment[] {
  const body = text.replace(/```[a-z]*\s*/gi, '').trim();
  const rows = jsonRows(body) ?? objectRows(body) ?? labelRows(body, names);
  const cast = new Map(names.map((name) => [name.toLowerCase(), name]));
  const seen = new Set<string>();
  const segments: ScriptSegment[] = [];
  for (const row of rows) {
    const speaker = String(row.speaker || '').replace(/\*+/g, '').trim();
    const line = String(row.text || '').trim();
    const key = line.toLowerCase().replace(/\s+/g, ' ');
    if (!speaker || !line || seen.has(key)) continue;
    seen.add(key);
    const pause = Number(row.pause_before_ms);
    const delivery = typeof row.delivery === 'string' ? row.delivery.trim() : '';
    segments.push({
      index: segments.length,
      speaker: cast.get(speaker.toLowerCase()) ?? speaker,
      text: line,
      ...(Number.isFinite(pause) && pause >= 0 && row.pause_before_ms != null ? { pause_before_ms: Math.round(pause) } : {}),
      ...(delivery ? { delivery_instruction: delivery } : {}),
    });
  }
  return segments;
}

type Row = { speaker?: unknown; text?: unknown; pause_before_ms?: unknown; delivery?: unknown };

function jsonRows(body: string): Row[] | null {
  const start = body.search(/[[{]/);
  if (start < 0) return null;
  const end = Math.max(body.lastIndexOf('}'), body.lastIndexOf(']'));
  try {
    const parsed = JSON.parse(body.slice(start, end + 1));
    const raw = Array.isArray(parsed) ? parsed : Array.isArray(parsed?.segments) ? parsed.segments : null;
    if (!raw) return null;
    const rows = raw.filter((row: unknown) => row && typeof row === 'object').map((row: Record<string, unknown>) => ({
      speaker: row.speaker ?? row.name,
      text: row.text ?? row.line ?? row.content,
      pause_before_ms: row.pause_before_ms,
      delivery: row.delivery_instruction ?? row.delivery,
    }));
    return rows.length ? rows : null;
  } catch {
    return null;
  }
}

const OBJECT = /\{\s*"(?:speaker|name)"\s*:\s*"((?:[^"\\]|\\.)*)"\s*,\s*"(?:text|line|content)"\s*:\s*"((?:[^"\\]|\\.)*)"\s*\}/g;

function objectRows(body: string): Row[] | null {
  const rows: Row[] = [];
  for (const match of body.matchAll(OBJECT)) {
    try {
      rows.push({ speaker: JSON.parse(`"${match[1]}"`), text: JSON.parse(`"${match[2]}"`) });
    } catch {}
  }
  return rows.length ? rows : null;
}

function labelRows(body: string, names: string[]): Row[] {
  const cast = new Set(names.map((name) => name.toLowerCase()));
  return body.split(/\r?\n/).flatMap((raw) => {
    const match = raw.match(/^\s*[-*]?\s*\**([^:*]{1,60}?)\**\s*:\s*\**\s*(.+)$/);
    if (!match || !cast.has(match[1].trim().toLowerCase())) return [];
    return [{ speaker: match[1].trim(), text: match[2].trim() }];
  });
}
