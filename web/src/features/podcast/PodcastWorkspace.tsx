/* eslint-disable @typescript-eslint/ban-ts-comment -- baseline WP-9.x */
/* eslint-disable @typescript-eslint/no-explicit-any -- baseline WP-9.x */
/* eslint-disable react-hooks/exhaustive-deps -- baseline WP-9.x */
// @ts-nocheck
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useRef, useState } from 'react';
import { omnixApiClient, type AssetListResponse, type JobRecord } from '../../api/client';
import type { OmnixModuleDefinition } from '../../app/modules';
import { WorkspacePanel } from '../../design/primitives';
import { FeatureSubmitFeedback, FeatureValidationMessage } from '../../shared/FeatureSubmitFeedback';
import { requestPodcastScript, scriptSummary, type ScriptSegment } from './podcastScript';
import { PodcastEpisodeSetup, defaultEpisode, formats, type EpisodeSettings } from './PodcastEpisodeSetup';
import { STOPPED_MESSAGE, cancelOnStop, isStopped, sleepUnlessStopped, throwIfStopped } from './podcastControl';
import { PodcastParticipants, defaultSpeakers, type SpeakerDraft } from './PodcastParticipants';
import { PodcastRunControls } from './PodcastRunControls';
import { PodcastOutputs, PodcastRunProgress, PodcastStudioHeader, PodcastTranscript, type TranscriptRow } from './PodcastStudioParts';
import { PodcastLibrary } from './PodcastLibrary';
import { clock, transcriptRows, type PodcastEpisode } from './podcastEpisodes';
import { activeStageIndex, jobSteps, type RunProgress } from './podcastProgress';
import { saveRunScript } from './podcastTakes';
import { lineAt, stitchedTimeline, timelineFrom, type LineStart } from './podcastTimeline';
import './PodcastWorkspace.css';
import { ApiError } from '../../api/errors';
import { fetchBytes } from '../../api/transport';
import { jobOutputRefs } from '../../api/schemas/streams';
import { downloadUrl } from '../../shared/download';
import { GatewayErrorNotice } from '../../shared/GatewayErrorNotice';
import { jobKeys } from '../../api/jobs';
import { voiceApiClient } from '../voice';
import { CastPortraitLoadControl, CharacterStage, listCastableCharacters, speakAsCharacters, type CastableCharacter, type CharacterSpeechRun } from '../assistant';

type VoiceAsset = AssetListResponse['assets'][number];
/** A script line; `line_id` names it in the run's saved script (`podcastTakes.ts`). */
type Segment = ScriptSegment & { line_id?: string };
type Output = {
  dataUrl: string;
  duration: number;
  jobId: string;
  key: string;
  title: string;
  live?: boolean;
  /** The script line a preview piece speaks (its position in the script). */
  line?: number;
  /** Where each line starts in this audio, for the transcript to follow (`podcastTimeline.ts`). */
  timeline?: LineStart[];
};

type WavChunk = {
  data: Uint8Array;
  sampleRate: number;
  channels: number;
  bitsPerSample: number;
};

const stitchedKey = 'live:stitched-preview';
// The player's phases while nothing plays: the cast speaking live (D4), then the final render.
const liveCastKey = '__live_cast__';
const finalRenderKey = '__final_render__';
const outputSettings = { speed: 1, pitch: 0, stability: 0.72, similarity: 0.78 };
const audioEffects = ['Compression', 'De-esser'];
/** The studio's lists load once; a run refreshes them when it finishes. */
const loadOnce = { retry: false, refetchInterval: false, refetchOnWindowFocus: false } as const;

const minutes = (value: string) => Math.max(1, Number.parseInt(value, 10) || 1);
const isTerminal = (status: unknown) => ['completed', 'complete', 'succeeded', 'success', 'done', 'failed', 'error', 'cancelled', 'canceled'].includes(String(status ?? '').toLowerCase());
// A voice is named by its asset id, which the TTS provider resolves (WP-4.10).
const voiceName = (asset: VoiceAsset) => String((asset as any).metadata?.profile_name || (asset as any).metadata?.name || String((asset as any).file_name || '').replace(/\.[^.]+$/, '') || 'Voice');
// The live voice socket speaks by the clone's speaker id, as a call does (characters/live_call._voice_speaker_id).
const speakerIdOf = (asset: VoiceAsset) => {
  const metadata = (asset as any).metadata || {};
  const named = [metadata.voice_clone_id, metadata.voice_id, metadata.speaker].map((value) => String(value || '').trim()).find((value) => value && value.toLowerCase() !== 'default');
  return named || String(asset.id || '').replace(/^voice-cloning:/, '').trim();
};
const voicesFrom = (assets: VoiceAsset[]) => assets.filter((asset) => asset.type === 'voice_profile').map((asset) => ({ id: String(asset.id || ''), label: voiceName(asset), speaker: speakerIdOf(asset) })).filter((voice) => voice.id);
const jobTitle = (job?: JobRecord) => String((job?.input_payload as any)?.title || job?.type || 'Podcast audio');

function stages() {
  return [
    { id: 'producer_plan', label: 'Producer Plan', resource_class: 'cpu', status: 'queued' },
    { id: 'performance_script', label: 'Performance Script', resource_class: 'cpu', status: 'queued' },
    { id: 'speaking_turns', label: 'Speaking Turns', resource_class: 'gpu:tts', status: 'queued' },
    { id: 'mix', label: 'Mix', resource_class: 'cpu', status: 'queued' },
    { id: 'podcast_renderer', label: 'Podcast Renderer', resource_class: 'cpu', status: 'queued' },
  ];
}

function outputsFrom(jobs: Array<JobRecord | undefined>): Output[] {
  return jobs.flatMap((job) => jobOutputRefs(job).map((ref, index) => {
    const url = typeof ref.data_url === 'string' ? ref.data_url : typeof ref.audio_url === 'string' ? ref.audio_url : '';
    if (!(url.startsWith('data:audio/') || url.startsWith('blob:') || url.startsWith('/api/'))) return null;
    return { dataUrl: url, duration: Number(ref.duration || 0), jobId: job?.id || 'job', key: `${job?.id}:${ref.asset_id || index}`, title: ref.title || jobTitle(job), timeline: timelineFrom(ref.timeline) };
  }).filter(Boolean));
}

/** Polls `job` until it has audio or settles; a stop (`signal`) cancels it and throws. */
async function waitJob(job: JobRecord, timeoutMs = 120000, onProgress?: OnJobProgress, pollMs = 1250, signal?: AbortSignal) {
  const forget = cancelOnStop(job, signal);
  try {
    return await pollJob(job, timeoutMs, onProgress, pollMs, signal);
  } finally {
    forget();
  }
}

type OnJobProgress = (message: string, progress?: JobRecord['progress']) => void;

async function pollJob(job: JobRecord, timeoutMs: number, onProgress: OnJobProgress | undefined, pollMs: number, signal?: AbortSignal) {
  let latest = job;
  let shown = '';
  const started = Date.now();
  while (!outputsFrom([latest]).length && !isTerminal(latest.status) && Date.now() - started < timeoutMs) {
    await sleepUnlessStopped(pollMs, signal);
    throwIfStopped(signal);
    try { latest = await omnixApiClient.getJob(job.id); } catch {}
    const message = String(latest.progress?.message || '').trim();
    if (onProgress && message && message !== shown) onProgress((shown = message), latest.progress);
  }
  return latest;
}

// The final render speaks every line in turn (about ten seconds a line on a local GPU, owner report 2026-11-24: a
// 20-minute episode outlived the old three-minute wait), so the wait grows with the script.
const FINAL_RENDER_MS_PER_LINE = 60000;
const FINAL_RENDER_MIN_MS = 15 * 60000;
export const finalRenderWaitMs = (lines: number) => Math.max(FINAL_RENDER_MIN_MS, lines * FINAL_RENDER_MS_PER_LINE);
// Tests shorten the final render's polling.
export const finalRenderTiming = { pollMs: 1250 };

function assignments(segments: Segment[], speakers: SpeakerDraft[], voices: Array<{ id: string; label: string }>) {
  return Object.fromEntries([...new Set(segments.map((segment) => segment.speaker))].map((name, index) => {
    const speaker = speakers.find((entry) => entry.name === name || entry.role === name) || speakers[index % Math.max(1, speakers.length)];
    return [name, { voiceId: speaker?.voice || voices[index % Math.max(1, voices.length)]?.id || null, style: speaker?.speakingStyle || speaker?.role || 'Neutral', speakerId: speaker?.id || null }];
  }));
}

const defaultVoices = (voices: any[]) => ({ narrator: voices[0]?.id || null, female: voices[1]?.id || voices[0]?.id || null, male: voices[2]?.id || voices[0]?.id || null });

function previewPayload(args: any) {
  const assignment = args.assignments[args.segment.speaker] || {};
  const voiceId = assignment.voiceId || args.voices[0]?.id || null;
  return {
    title: `${args.title} - ${args.segment.speaker} ${args.segment.index + 1}`,
    text: args.segment.text,
    provider_id: null,
    speaker: args.segment.speaker,
    voice_id: voiceId,
    language: args.language,
    script_mode: 'single_speaker',
    script_speakers: [{ name: args.segment.speaker, count: 1 }],
    script_segments: [args.segment],
    character_voice_assignments: [{ speaker: args.segment.speaker, voice_id: voiceId, style: assignment.style || 'Neutral', line_count: 1 }],
    voice_mapping: { [args.segment.speaker]: voiceId },
    default_voices: defaultVoices(args.voices),
    output_settings: outputSettings,
    audio_effects: audioEffects,
    save_output: true,
    // Spoken under its saved line, the voice job keeps this audio as the line's take for the final render.
    ...(args.scriptId ? { script_id: args.scriptId } : {}),
    renderer: 'podcast-live-preview',
  };
}

function finalPayload(args: any) {
  const counts = args.segments.reduce((acc: any, segment: Segment) => ({ ...acc, [segment.speaker]: (acc[segment.speaker] || 0) + 1 }), {});
  const names = Object.keys(counts);
  const map = Object.fromEntries(names.map((name) => [name, args.assignments[name]?.voiceId || null]));
  return {
    title: args.title,
    brief: args.brief,
    format: args.format,
    audience: args.audience,
    duration_minutes: minutes(args.duration),
    target_duration_seconds: minutes(args.duration) * 60,
    target_word_count: minutes(args.duration) * 150,
    tone: args.tone,
    language: args.language,
    generation_style: args.generationStyle,
    review_policy: { mode: args.generationStyle },
    renderer: 'podcast',
    text: args.segments.map((segment: Segment) => `${segment.speaker}: ${segment.text}`).join('\n'),
    provider_id: null,
    speaker: names[0] || args.speakers[0]?.name || 'Host',
    voice_id: map[names[0]] || args.voices[0]?.id || null,
    script_mode: args.segments.length > 1 ? 'multi_speaker' : 'single_speaker',
    script_speakers: names.map((name) => ({ name, count: counts[name] })),
    script_segments: args.segments,
    // An opening and closing sting and room tone under the voices (voice/bookends.py); off unless asked for.
    ...(args.bookends ? { bookends: true } : {}),
    ...(args.roomTone ? { room_tone: true } : {}),
    // No line asked again: every take the preview kept is reused, and only lines without one are spoken.
    ...(args.scriptId ? { script_id: args.scriptId, render_line_ids: [] } : {}),
    character_voice_assignments: names.map((name) => ({ speaker: name, voice_id: map[name] || null, style: args.assignments[name]?.style || 'Neutral', line_count: counts[name] })),
    voice_mapping: map,
    default_voices: defaultVoices(args.voices),
    output_settings: outputSettings,
    audio_effects: audioEffects,
    save_output: true,
    speakers: args.speakers.map((speaker: SpeakerDraft) => ({ id: speaker.id, name: speaker.name, role: speaker.role, speakerInstructions: speaker.instructions, voiceMapping: { speakerId: speaker.id, voiceId: speaker.voice } })),
    constraints: { maxSpeakerTurnSeconds: 45 },
  };
}

function readAscii(view: DataView, offset: number, length: number) {
  let value = '';
  for (let index = 0; index < length && offset + index < view.byteLength; index += 1) value += String.fromCharCode(view.getUint8(offset + index));
  return value;
}

function writeAscii(bytes: Uint8Array, offset: number, value: string) {
  for (let index = 0; index < value.length; index += 1) bytes[offset + index] = value.charCodeAt(index);
}

function parseWavChunk(bytes: Uint8Array): WavChunk {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  if (bytes.byteLength >= 44 && readAscii(view, 0, 4) === 'RIFF' && readAscii(view, 8, 4) === 'WAVE') {
    let cursor = 12;
    let sampleRate = 24000;
    let channels = 1;
    let bitsPerSample = 16;
    let data: Uint8Array | null = null;

    while (cursor + 8 <= view.byteLength) {
      const id = readAscii(view, cursor, 4);
      const size = view.getUint32(cursor + 4, true);
      const start = cursor + 8;
      const end = Math.min(start + size, bytes.byteLength);

      if (id === 'fmt ' && size >= 16 && start + 16 <= view.byteLength) {
        channels = view.getUint16(start + 2, true) || 1;
        sampleRate = view.getUint32(start + 4, true) || 24000;
        bitsPerSample = view.getUint16(start + 14, true) || 16;
      }
      if (id === 'data' && end > start) data = bytes.slice(start, end);
      cursor = end + (size % 2);
    }

    if (data) return { data, sampleRate, channels, bitsPerSample };
  }

  return { data: bytes, sampleRate: 24000, channels: 1, bitsPerSample: 16 };
}

function createWavBytes(chunks: WavChunk[]) {
  const first = chunks[0] ?? { sampleRate: 24000, channels: 1, bitsPerSample: 16, data: new Uint8Array() };
  const sampleRate = first.sampleRate || 24000;
  const channels = first.channels || 1;
  const bitsPerSample = first.bitsPerSample || 16;
  const blockAlign = Math.max(1, Math.floor((channels * bitsPerSample) / 8));
  const byteRate = sampleRate * blockAlign;
  const dataSize = chunks.reduce((sum, chunk) => sum + chunk.data.byteLength, 0);
  const bytes = new Uint8Array(44 + dataSize);
  const view = new DataView(bytes.buffer);

  writeAscii(bytes, 0, 'RIFF');
  view.setUint32(4, 36 + dataSize, true);
  writeAscii(bytes, 8, 'WAVE');
  writeAscii(bytes, 12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, channels, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, byteRate, true);
  view.setUint16(32, blockAlign, true);
  view.setUint16(34, bitsPerSample, true);
  writeAscii(bytes, 36, 'data');
  view.setUint32(40, dataSize, true);

  let offset = 44;
  for (const chunk of chunks) {
    bytes.set(chunk.data, offset);
    offset += chunk.data.byteLength;
  }

  const computedDuration = dataSize / Math.max(1, byteRate);
  return { bytes, duration: computedDuration };
}

async function loadAudioBytes(url: string) {
  const response = await fetchBytes(url).catch((error: unknown) => {
    throw error instanceof ApiError ? new Error(`Audio fetch failed: ${error.status}`) : error;
  });
  return new Uint8Array(await response.arrayBuffer());
}

async function stitchOutputs(outputs: Output[]) {
  if (!outputs.length) return null;
  const chunks: WavChunk[] = [];
  for (const output of outputs) chunks.push(parseWavChunk(await loadAudioBytes(output.dataUrl)));
  const wav = createWavBytes(chunks);
  const blobUrl = URL.createObjectURL(new Blob([wav.bytes], { type: 'audio/wav' }));
  const dataBytes = Math.max(1, chunks.reduce((sum, chunk) => sum + chunk.data.byteLength, 0));
  const timeline = stitchedTimeline(outputs.map((output, index) => output.line ?? index), chunks.map((chunk) => (chunk.data.byteLength / dataBytes) * wav.duration));
  const last = outputs[outputs.length - 1];
  const summedDuration = outputs.reduce((sum, output) => sum + Number(output.duration || 0), 0);
  return {
    ...last,
    dataUrl: blobUrl,
    key: `${stitchedKey}:${outputs.length}:${last.key}`,
    title: `Live preview stitched ${outputs.length} / ${outputs.length}`,
    live: true,
    duration: wav.duration || summedDuration || last.duration,
    timeline,
  };
}

/** What one run reads from the studio and how it reports back (the workspace's state setters and player refs). */
type ProductionRun = {
  episode: EpisodeSettings;
  speakers: SpeakerDraft[];
  voices: Array<{ id: string; label: string; speaker: string }>;
  signal?: AbortSignal;
  /** Live avatars are on and someone is cast: the cast speaks the preview instead of stitched audio. */
  liveCast: boolean;
  castOf: (speaker: SpeakerDraft | undefined) => CastableCharacter | undefined;
  ttsSpeaker: (voiceAssetId: string | null) => string | null;
  stageKey: string;
  pausedRef: { current: boolean };
  speechRunRef: { current: CharacterSpeechRun | null };
  piecesRef: { current: Output[] };
  queue: (output: Output) => Promise<void>;
  say: (message: string) => void;
  direct: (note: string) => void;
  select: (key: string) => void;
  showScript: (rows: TranscriptRow[]) => void;
  /** Moves the run's progress bar (`podcastProgress.ts`). */
  advance: (progress: RunProgress) => void;
  onSpeaking: (id: string | null) => void;
  onLiveSpeech: (on: boolean) => void;
  /** The line the cast is speaking, for the transcript to follow; null when it stops. */
  onLine: (line: number | null) => void;
};

/** One podcast run: the script, the live preview (stitched audio or the cast speaking), then the final render. */
async function producePodcast(run: ProductionRun): Promise<JobRecord> {
  const { voices, signal, speakers } = run;
  const { title, brief, audience, format, tone, duration, language, generationStyle, sources, bookends, roomTone } = run.episode;
  run.advance({ stage: 'script', done: 0, total: 1, label: 'Writing the script' });
  const script = await requestPodcastScript(
    { title, brief, audience, format, tone, durationMinutes: minutes(duration), speakers, sources },
    { onProgress: (step, steps) => {
      run.say(`Writing the podcast script: ${step.toLowerCase()}...`);
      run.advance({ stage: 'script', ...jobSteps(steps), label: `Script: ${step}` });
    }, signal },
  );
  const segments = script.segments;
  const summary = scriptSummary(script.quality, script.model);
  const asg = assignments(segments, speakers, voices);
  run.showScript(transcriptRows(segments, minutes(duration) * 60));
  run.select('__streaming__');
  // Preview lines become the saved script's takes, so the final render reuses them (`podcastTakes.ts`). The cast
  // speaks live and keeps no takes, so a live-avatar run still has every line spoken by the final render.
  const saved = run.liveCast ? null : await saveRunScript(title, segments);
  throwIfStopped(signal);
  const reuse = Boolean(saved);
  const lined: Segment[] = saved ? segments.map((segment, position) => ({ ...segment, line_id: saved.lineIds[position] })) : segments;
  if (run.liveCast) {
    // D4: the cast speaks the script live, each line in its speaker's voice and with its avatar; the final render
    // below is the same either way.
    run.direct(`Script is ready${summary}. The cast is speaking it live with their avatars; the final render follows.`);
    const lines = segments.map((segment) => {
      const assignment = asg[segment.speaker] || {};
      const character = run.castOf(speakers.find((speaker) => speaker.id === assignment.speakerId));
      return { text: segment.text, voiceId: run.ttsSpeaker(assignment.voiceId || null), speaker: character ? { id: character.id, pack: character.pack } : null };
    });
    const speech = speakAsCharacters(run.stageKey, lines, (index, line) => {
      run.onSpeaking(line.speaker?.id ?? null);
      run.onLine(index);
      run.say(`Live ${index + 1}/${lines.length}: ${segments[index].speaker}`);
      run.advance({ stage: 'preview', done: index, total: lines.length, label: `Live: line ${index + 1} of ${lines.length} (${segments[index].speaker})` });
    });
    run.speechRunRef.current = speech;
    if (run.pausedRef.current) speech.pause();
    const stopSpeech = () => speech.stop();
    signal?.addEventListener('abort', stopSpeech, { once: true });
    run.onLiveSpeech(true);
    // No preview audio is stitched on this path: the player says so instead of waiting for a segment.
    run.select(liveCastKey);
    try {
      await speech.done;
    } finally {
      signal?.removeEventListener('abort', stopSpeech);
      if (run.speechRunRef.current === speech) run.speechRunRef.current = null;
      run.onLiveSpeech(false);
      run.onSpeaking(null);
      run.onLine(null);
    }
    throwIfStopped(signal);
  } else {
    run.direct(`Script is ready${summary}. Each completed preview turn is stitched into one growing WAV so the audio duration extends instead of resetting to the latest segment.`);
    run.advance({ stage: 'preview', done: 0, total: segments.length, label: `Preview: line 1 of ${segments.length}`, reuse });

    for (const [position, segment] of lined.entries()) {
      throwIfStopped(signal);
      const job = await omnixApiClient.createJob({
        module: 'podcast',
        type: 'tts.synthesize',
        resource_class: 'gpu:tts',
        priority: 1,
        input_payload: previewPayload({ title, language, segment, voices, assignments: asg, scriptId: saved?.scriptId }),
        stages: stages().slice(0, 3),
      }, { timeoutMs: 120000, timeoutMessage: 'Podcast live preview turn is still running.' });
      const output = outputsFrom([await waitJob(job, 120000, undefined, 1250, signal)])[0];
      if (output) {
        await run.queue({ ...output, key: `live:${segment.index}:${output.key}`, title: `${segment.speaker}: voice mapped`, live: true, line: position });
        run.say(`Stitched live preview ${segment.index + 1}/${segments.length}: ${segment.speaker}`);
      }
      const made = position + 1;
      run.advance({ stage: 'preview', done: made, total: segments.length, label: `Preview: line ${Math.min(made + 1, segments.length)} of ${segments.length}`, reuse });
    }
  }
  throwIfStopped(signal);
  if (!run.piecesRef.current.length) run.select(finalRenderKey);

  const finalJob = await omnixApiClient.createJob({
    module: 'podcast',
    type: 'tts.multi_speaker_synthesize',
    resource_class: 'gpu:tts',
    priority: 0,
    input_payload: finalPayload({ title, brief, format, audience, duration, tone, language, generationStyle, speakers, voices, assignments: asg, segments: lined, bookends, roomTone, scriptId: saved?.scriptId }),
    stages: stages(),
  }, { timeoutMs: 180000, timeoutMessage: 'Final podcast render is still running.' });
  run.say(`Rendering the final podcast audio: ${segments.length} lines...`);
  run.advance({ stage: 'final', done: 0, total: 1, reuse, label: reuse ? 'Final render: mixing the preview lines' : `Final render: waiting for the voice engine (${segments.length} lines)` });
  return waitJob(finalJob, finalRenderWaitMs(segments.length), (step, steps) => {
    run.say(`Rendering the final podcast audio: ${step.toLowerCase()}...`);
    run.advance({ stage: 'final', ...jobSteps(steps), label: `Final render: ${step}`, reuse });
  }, finalRenderTiming.pollMs, signal);
}

export function PodcastWorkspace({ module }: { module: OmnixModuleDefinition }) {
  const queryClient = useQueryClient();
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const currentRef = useRef<Output | null>(null);
  const pendingRef = useRef<Output | null>(null);
  const resumeNextRef = useRef(false);
  const userPausedRef = useRef(false);
  const autoStartedRef = useRef(false);
  const restoreRef = useRef({ time: 0, play: false });
  const piecesRef = useRef<Output[]>([]);
  const stitchRunRef = useRef(0);
  const liveBlobUrlsRef = useRef<string[]>([]);
  const speechRunRef = useRef<CharacterSpeechRun | null>(null);
  // The producer's Stop and Pause for the run in progress (owner request 2026-11-24).
  const stopRef = useRef<AbortController | null>(null);
  const pausedRef = useRef(false);
  const [paused, setPausedState] = useState(false);
  const setPaused = (value: boolean) => { pausedRef.current = value; setPausedState(value); };
  const [stopping, setStopping] = useState(false);
  // The stage's run key: "Load live avatars" keeps the cast's idle loops under it, and every run speaks under it, so
  // its speakers share one portrait lease and the loops loaded before the run are the run's.
  const stageKeyRef = useRef(`podcast-stage:${Math.random().toString(36).slice(2, 10)}`);

  const jobsQuery = useQuery({ queryKey: jobKeys.all, queryFn: () => omnixApiClient.listJobs(), ...loadOnce });
  // Every clone in the voice library, as the chat lists them: stored voice profiles miss clones that exist only on
  // disk (owner report 2026-11-23: Ehsan, Afra and Rudeus were missing). Older gateways have only the stored list.
  const assetsQuery = useQuery({ queryKey: ['podcast', 'voice-library'], queryFn: () => voiceApiClient.listVoiceLibrary().catch(() => omnixApiClient.listAssets({ type: 'voice_profile' })), ...loadOnce });
  const charactersQuery = useQuery({ queryKey: ['podcast', 'characters'], queryFn: listCastableCharacters, ...loadOnce });

  const [episode, setEpisode] = useState(defaultEpisode);
  const { title, brief, duration, format } = episode;
  const [speakers, setSpeakers] = useState(defaultSpeakers);
  const [rows, setRows] = useState<any[]>([]);
  const [directorNote, setDirectorNote] = useState('No live production is running. Configure the episode, then press Generate live podcast.');
  const [liveCommand, setLiveCommand] = useState('');
  const [playbackRate, setPlaybackRate] = useState('1.0x');
  const [selectedOutputKey, setSelectedOutputKey] = useState('');
  const [pieces, setPieces] = useState<Output[]>([]);
  const [current, setCurrent] = useState<Output | null>(null);
  const [autoplay, setAutoplay] = useState(false);
  const [message, setMessage] = useState('Ready for automatic production.');
  const [liveAvatars, setLiveAvatars] = useState(false);
  const [speakingId, setSpeakingId] = useState<string | null>(null);
  const [liveSpeech, setLiveSpeech] = useState(false);
  const [progress, setProgress] = useState<RunProgress | null>(null);
  const [activeLine, setActiveLine] = useState<number | null>(null);

  const voices = useMemo(() => voicesFrom(assetsQuery.data?.assets ?? []), [assetsQuery.data?.assets]);
  const podcastJobs = jobsQuery.data?.jobs?.filter((job: JobRecord) => job.module === 'podcast') ?? [];
  const characters: CastableCharacter[] = charactersQuery.data ?? [];
  const castOf = (speaker: SpeakerDraft | undefined) => (speaker?.characterId ? characters.find((character) => character.id === speaker.characterId) : undefined);
  const cast = speakers.map((speaker) => castOf(speaker)).filter(Boolean).map((character) => ({ id: character.id, name: character.name, pack: character.pack }));
  const stageCast = cast.filter((member, index) => cast.findIndex((other) => other.id === member.id) === index);
  const ttsSpeaker = (voiceAssetId: string | null) => (voiceAssetId ? voices.find((voice) => voice.id === voiceAssetId)?.speaker || voiceAssetId.replace(/^voice-cloning:/, '') : null);

  function install(output: Output, time = audioRef.current?.currentTime || 0, play = false) {
    restoreRef.current = { time, play };
    currentRef.current = output;
    setCurrent(output);
    setActiveLine(lineAt(output.timeline, time));
    setSelectedOutputKey(output.key);
  }

  async function queue(output: Output) {
    const nextPieces = [...piecesRef.current, output];
    piecesRef.current = nextPieces;
    setPieces(nextPieces);
    setSelectedOutputKey(stitchedKey);

    const stitchRun = ++stitchRunRef.current;
    const joined = await stitchOutputs(nextPieces).catch((error) => {
      console.warn('[PODCAST] Failed to stitch live preview audio:', error);
      return null;
    });
    if (!joined || stitchRun !== stitchRunRef.current) {
      if (joined?.dataUrl?.startsWith('blob:')) URL.revokeObjectURL(joined.dataUrl);
      return;
    }

    liveBlobUrlsRef.current.push(joined.dataUrl);
    const audio = audioRef.current;
    const restoreTime = currentRef.current?.duration || audio?.currentTime || 0;
    if (currentRef.current?.live && audio && !audio.paused && !audio.ended) {
      pendingRef.current = joined;
      return;
    }

    const play = Boolean(currentRef.current?.live && resumeNextRef.current && !userPausedRef.current);
    resumeNextRef.current = false;
    pendingRef.current = null;
    install(joined, restoreTime, play);
  }

  function resetPreview() {
    try { if (audioRef.current?.getAttribute('src')) audioRef.current.pause(); } catch {}
    stitchRunRef.current += 1;
    pendingRef.current = null;
    resumeNextRef.current = false;
    userPausedRef.current = false;
    autoStartedRef.current = false;
    currentRef.current = null;
    piecesRef.current = [];
    for (const url of liveBlobUrlsRef.current) URL.revokeObjectURL(url);
    liveBlobUrlsRef.current = [];
    setCurrent(null);
    setPieces([]);
  }

  const createJobMutation = useMutation({
    mutationFn: async (): Promise<JobRecord | null> => {
      try {
        return await produce();
      } catch (error) {
        // Stop is the producer's choice, not a failure: the run ends with what it has (null, see onSuccess).
        if (isStopped(error)) return null;
        throw error;
      }
    },
    onMutate: () => {
      resetPreview();
      stopRef.current = new AbortController();
      setPaused(false);
      setRows([]);
      setActiveLine(null);
      setAutoplay(false);
      setSelectedOutputKey('__script__');
      setDirectorNote(`Writing a ${minutes(duration)}-minute script with the podcast model. A long episode can take a few minutes.`);
      setMessage('Writing the podcast script...');
    },
    onSuccess: async (job) => {
      if (!job) {
        setDirectorNote('Stopped. Nothing more is generated; any stitched preview stays in the player.');
        setMessage(STOPPED_MESSAGE);
        if (!currentRef.current) setSelectedOutputKey('__new__');
        await queryClient.invalidateQueries({ queryKey: jobKeys.all });
        return;
      }
      const output = outputsFrom([job])[0];
      // The final render takes the player unless a stitched preview is still being listened to (owner report
      // 2026-11-23: after a live-avatar run nothing was stitched, so the player waited for a segment that never came).
      const audio = audioRef.current;
      const previewHeld = Boolean(currentRef.current && !(audio?.ended && !pendingRef.current));
      if (output && !previewHeld) install(output, 0);
      const stillRunning = !output && !isTerminal(job.status);
      setDirectorNote(stillRunning ? 'The final render is still running. It appears in the library when it finishes.'
        : !output ? 'Podcast render completed but no playable audio output was attached.'
          : previewHeld ? 'Final podcast audio is ready. The stitched live preview stays active until you select the final render.'
            : 'Final podcast audio is ready.');
      setMessage(output ? `Podcast audio ready: ${job.id}`
        : stillRunning ? `Final podcast render is still running: ${job.id}`
          : `Podcast production completed without playable audio: ${job.id}`);
      await Promise.all([queryClient.invalidateQueries({ queryKey: jobKeys.all }), queryClient.invalidateQueries({ queryKey: ['platform', 'assets'] })]);
    },
    onError: (error) => {
      setDirectorNote(error instanceof Error ? error.message : 'Podcast request failed.');
      setMessage(error instanceof Error ? error.message : 'Podcast request failed.');
    },
    onSettled: () => {
      stopRef.current = null;
      setStopping(false);
      setPaused(false);
    },
  });

  const produce = () => producePodcast({
    episode, speakers, voices, signal: stopRef.current?.signal, liveCast: liveAvatars && stageCast.length > 0, castOf, ttsSpeaker, stageKey: stageKeyRef.current,
    pausedRef, speechRunRef, piecesRef, queue, say: setMessage, direct: setDirectorNote, select: setSelectedOutputKey,
    showScript: (scriptRows) => { setRows(scriptRows); setAutoplay(true); }, onSpeaking: setSpeakingId, onLiveSpeech: setLiveSpeech, advance: setProgress, onLine: setActiveLine,
  });

  const connectedJob = createJobMutation.data ?? podcastJobs[0];
  const liveStatus = createJobMutation.isPending ? (selectedOutputKey === '__script__' ? 'SCRIPTING' : selectedOutputKey === finalRenderKey ? 'RENDERING' : 'STREAMING') : connectedJob ? String(connectedJob.status).toUpperCase() : 'IDLE';
  const liveActive = createJobMutation.isPending || Boolean(podcastJobs.find((job) => !isTerminal(job.status)));
  const runningStage = activeStageIndex(progress?.stage);
  const visibleStages = createJobMutation.isPending ? stages().map((stage, index) => ({ ...stage, state: index < runningStage ? 'done' : index === runningStage ? 'active' : 'pending' })) : stages().map((stage) => ({ ...stage, state: 'pending' }));

  useEffect(() => { currentRef.current = current; }, [current]);
  useEffect(() => () => { for (const url of liveBlobUrlsRef.current) URL.revokeObjectURL(url); }, []);
  useEffect(() => () => speechRunRef.current?.stop(), []);
  useEffect(() => { if (voices.length) setSpeakers((currentSpeakers) => currentSpeakers.map((speaker, index) => speaker.voice && voices.some((voice) => voice.id === speaker.voice) ? speaker : { ...speaker, voice: voices[index % voices.length].id })); }, [voices.map((voice) => voice.id).join('|')]);
  useEffect(() => {
    const audio = audioRef.current;
    if (!audio || !current) return;
    audio.playbackRate = Number.parseFloat(playbackRate) || 1;
    if (!autoplay || !current.live || autoStartedRef.current) return;
    autoStartedRef.current = true;
    const timer = window.setTimeout(() => audio.play()?.catch?.(() => setMessage('Audio is ready. Press play if the browser blocked autoplay.')), 50);
    return () => window.clearTimeout(timer);
  }, [current?.key, current?.dataUrl, autoplay, playbackRate]);

  function onPause() {
    const audio = audioRef.current;
    if (naturalEnd(audio) && createJobMutation.isPending) return;
    userPausedRef.current = true;
    if (createJobMutation.isPending && !stopRef.current?.signal.aborted) setPaused(true);
    resumeNextRef.current = false;
    if (pendingRef.current && (!audio || audio.paused || audio.ended)) {
      install(pendingRef.current, audio?.currentTime || 0, false);
      pendingRef.current = null;
    }
  }
  function onLoaded(event: any) {
    const audio = event.currentTarget;
    const restore = restoreRef.current;
    audio.playbackRate = Number.parseFloat(playbackRate) || 1;
    if (restore.time) audio.currentTime = Math.min(restore.time + (restore.play ? 0.02 : 0), Math.max(0, audio.duration - 0.05));
    if (restore.play) audio.play()?.catch?.(() => setMessage('Audio is ready. Press play if the browser blocked autoplay.'));
    restoreRef.current = { time: 0, play: false };
  }
  function onEnded() {
    const audio = audioRef.current;
    if (pendingRef.current) {
      const next = pendingRef.current;
      pendingRef.current = null;
      install(next, currentRef.current?.duration || audio?.currentTime || 0, !userPausedRef.current);
      return;
    }
    if (currentRef.current?.live && createJobMutation.isPending && !userPausedRef.current) {
      resumeNextRef.current = true;
      setMessage('Waiting for the next stitched preview chunk...');
      return;
    }
    const finalOutput = outputsFrom([createJobMutation.data, ...podcastJobs]).find((output) => !output.live);
    if (finalOutput) install(finalOutput);
  }

  function startGeneration() { if (brief.trim()) createJobMutation.mutate(); }
  /** Pause what is playing: the stitched preview at once, the cast once its current line ends. Generation goes on. */
  function pauseProduction() {
    setPaused(true);
    userPausedRef.current = true;
    resumeNextRef.current = false;
    speechRunRef.current?.pause();
    const audio = audioRef.current;
    if (audio && !audio.paused) audio.pause();
    setMessage(speechRunRef.current ? 'Paused; the cast stops after this line.' : 'Paused. Generation continues in the background.');
  }
  function resumeProduction() {
    setPaused(false);
    userPausedRef.current = false;
    speechRunRef.current?.resume();
    const audio = audioRef.current;
    if (pendingRef.current) {
      const next = pendingRef.current;
      pendingRef.current = null;
      install(next, audio?.currentTime || 0, true);
    } else if (audio && currentRef.current && !audio.ended) {
      audio.play()?.catch?.(() => setMessage('Audio is ready. Press play if the browser blocked autoplay.'));
    } else {
      // Caught up with the stitched preview: the next line plays when it arrives.
      resumeNextRef.current = true;
    }
    setMessage('Resumed.');
  }
  /** Stop the run: cancels the job in flight and starts nothing after it, the final render included. */
  function stopProduction() {
    stopRef.current?.abort();
    setStopping(true);
    setPaused(false);
    const audio = audioRef.current;
    if (audio && !audio.paused) audio.pause();
    setMessage('Stopping...');
  }
  function stopLiveAvatars() { speechRunRef.current?.stop(); setMessage('Live avatars stopped; the final render continues.'); }
  function resetPodcast() { resetPreview(); setEpisode((current) => ({ ...current, title: '', brief: '', duration: '5 min' })); setRows([]); setSelectedOutputKey('__new__'); setMessage('New podcast ready.'); }
  function submitLiveCommand() {
    const text = liveCommand.trim();
    if (text) {
      setDirectorNote(`Director note: ${text}`);
      setRows((currentRows) => [...currentRows, { timestamp: clock(currentRows.length * 15), speaker: 'Director', text }]);
      setLiveCommand('');
    }
  }
  function playEpisode(episode: PodcastEpisode, episodeRows: TranscriptRow[], timeline: LineStart[]) { install({ dataUrl: episode.audioUrl, duration: episode.durationSeconds, jobId: episode.jobId, key: `${episode.jobId}:${episode.assetId}`, title: episode.title, timeline }, 0, true); setRows(episodeRows); }
  function downloadCurrentOutput(label = 'Podcast audio') { if (!current) return; downloadUrl(current.dataUrl, `${title || 'podcast-output'}.wav`); setMessage(`${label}: download started.`); }
  async function copyEpisodeLink() { try { await navigator.clipboard?.writeText(`${location.href.split('#')[0]}#${connectedJob?.id ?? 'podcast'}`); setMessage('Podcast link copied.'); } catch {} }

  return (
    <WorkspacePanel labelledBy="module-title" className="podcast-workspace-panel">
      <div className="podcast-studio-shell">
        <PodcastStudioHeader label={module.label} />
        <GatewayErrorNotice label="Podcast jobs and voices" errors={[jobsQuery.error, assetsQuery.error]} />

        <div className="podcast-studio-grid">
          <section className="podcast-studio-stack">
            <PodcastEpisodeSetup episode={episode} setEpisode={setEpisode} onNewPodcast={resetPodcast} />

            <PodcastParticipants speakers={speakers} setSpeakers={setSpeakers} voices={voices} characters={characters} stageCastCount={stageCast.length} liveAvatars={liveAvatars} onLiveAvatars={setLiveAvatars} locked={createJobMutation.isPending} />

            <form onSubmit={(event) => { event.preventDefault(); startGeneration(); }}>
              <button className="podcast-generate-button" type="submit" disabled={createJobMutation.isPending}>Generate live podcast</button>
            </form>
            <FeatureValidationMessage show={brief.trim().length === 0 && !createJobMutation.isIdle} message="Enter an episode brief before generating a podcast." />
            <FeatureSubmitFeedback error={createJobMutation.error} errorPrefix="Podcast request" isError={createJobMutation.isError} isPending={createJobMutation.isPending} jobId={createJobMutation.data?.id} pendingMessage="Generating script and stitching preview audio..." successPrefix="Podcast production queued" />
            {createJobMutation.isPending && progress ? <PodcastRunProgress progress={progress} /> : null}
          </section>

          <section className="podcast-live-column">
            <article className={`podcast-card live-production-card ${liveActive ? 'streaming' : 'idle'}`}>
              <div className="card-heading-row"><h3>Live production</h3><span className="auto-badge">{liveStatus}</span></div>
              <div className="stage-rail">{visibleStages.map((stage, index) => <span key={stage.id} className={stage.state}>{stage.state === 'done' ? 'OK' : index + 1}<small>{stage.label}</small></span>)}</div>
              <div className="director-note"><b>Director</b><span>{directorNote}</span></div>
              {createJobMutation.isPending ? <PodcastRunControls paused={paused} stopping={stopping} onPause={pauseProduction} onResume={resumeProduction} onStop={stopProduction} /> : null}
              {liveAvatars && stageCast.length ? (
                <section className="podcast-live-avatars">
                  <CharacterStage members={stageCast} speakingId={speakingId} />
                  {liveSpeech ? <button className="ghost-button compact" type="button" onClick={stopLiveAvatars}>Stop live avatars</button> : <CastPortraitLoadControl runKey={stageKeyRef.current} members={stageCast} disabled={createJobMutation.isPending} />}
                </section>
              ) : null}

              <PodcastTranscript rows={rows} activeIndex={activeLine} />

              <div role="group" className="podcast-audio-player" aria-label="Podcast audio player">
                <div className="audio-player-heading">
                  <span>{current ? current.title : selectedOutputKey === '__script__' ? 'Generating podcast script...' : selectedOutputKey === liveCastKey ? 'The cast is speaking live; the final render follows.' : selectedOutputKey === finalRenderKey ? 'Rendering the final podcast audio...' : selectedOutputKey === '__streaming__' || selectedOutputKey === stitchedKey ? 'Waiting for first stitched live audio segment...' : 'No podcast audio yet'}</span>
                  <small>{current?.live ? `LIVE STITCHED ${pieces.length} / ${rows.length || pieces.length}` : current ? 'AUDIO READY' : createJobMutation.isPending ? liveStatus : 'Generate a completed podcast to enable playback'}</small>
                </div>
                <audio key={current?.key || selectedOutputKey || 'podcast-empty-audio'} ref={audioRef} src={current?.dataUrl || undefined} controls preload="auto" onLoadedMetadata={onLoaded} onCanPlay={() => current && setMessage(`${current.live ? 'Stitched live preview' : 'Audio available'}: ${current.title}`)} onPause={onPause} onTimeUpdate={(event) => setActiveLine(lineAt(current?.timeline, event.currentTarget.currentTime))} onPlay={() => { userPausedRef.current = false; if (pausedRef.current && !speechRunRef.current) setPaused(false); }} onEnded={onEnded} />
                <div className="audio-toolbar"><label>Playback speed<select value={playbackRate} onChange={(event) => setPlaybackRate(event.target.value)}><option>0.8x</option><option>1.0x</option><option>1.25x</option></select></label><small>{current ? `${clock(current.duration)} ${current.live ? 'stitched preview' : 'rendered'}` : 'No audio loaded'}</small></div>
              </div>

              <form className="live-command" onSubmit={(event) => { event.preventDefault(); submitLiveCommand(); }}><input value={liveCommand} onChange={(event) => setLiveCommand(event.target.value)} placeholder="Add a production note" /><button type="submit" disabled={!liveCommand.trim()}>Apply</button></form>
            </article>

            <PodcastOutputs title={title} status={connectedJob ? String(connectedJob.status).toUpperCase() : createJobMutation.isPending ? liveStatus : 'IDLE'} summary={`${formats.find((option) => option.id === format)?.label} - ${speakers.length} voices - ${duration}`} playing={current?.title ?? null} onDownload={downloadCurrentOutput} onNote={setMessage} onCopyLink={() => void copyEpisodeLink()} />
          </section>

          <PodcastLibrary playingJobId={current && !current.live ? current.jobId : null} disabled={createJobMutation.isPending} onPlay={playEpisode} />
        </div>
        <p className="action-toast" role="status">{message}</p>
      </div>
    </WorkspacePanel>
  );
}

/** Whether playback reached the end of the audio (not a pause near it). */
function naturalEnd(audio: HTMLAudioElement | null) { return Boolean(audio && Number.isFinite(audio.duration) && audio.duration > 0 && audio.currentTime >= audio.duration - 0.18); }
