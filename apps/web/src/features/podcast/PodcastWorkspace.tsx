// @ts-nocheck
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useRef, useState } from 'react';
import { omnixApiClient, type AssetListResponse, type JobRecord } from '../../api/client';
import type { OmnixModuleDefinition } from '../../app/modules';
import { OmnixStatusPill, WorkspacePanel } from '../../design/primitives';
import { mockPodcastRelationships, mockPodcastSpeakerProfiles } from '../conversation-production/speakers';
import { FeatureSubmitFeedback, FeatureValidationMessage } from '../shared/FeatureSubmitFeedback';
import { mockProductionAssetTiles, mockQualityGates, mockRecentPodcastJobs, mockSessionMetrics } from './mockProduction';
import { buildReviewPolicy, generationStyleOptions, reviewStopOptions } from './reviewPolicy';
import { buildConversationalPodcastSegments } from './scriptBuilder';
import type { PodcastFormat } from './types';
import './PodcastWorkspace.css';
import './PodcastWorkspaceLayoutFix.css';

type VoiceAsset = AssetListResponse['assets'][number];
type SpeakerDraft = ReturnType<typeof toSpeakerDraft>;
type SidebarPanel = 'quality' | 'health' | 'recent';
type TranscriptRow = { timestamp: string; speaker: string; text: string };
type PlayablePodcastOutput = { dataUrl: string; duration: number; jobId: string; key: string; title: string };
type RelationshipConfig = { hostLabel: string; guestALabel: string; guestBLabel: string; moderation: string; respect: string; disagreement: string };

const defaultTitle = 'The Future of AI in Everyday Life';
const defaultBrief = 'Explore how artificial intelligence is shaping our daily lives, transforming work and productivity, inspiring creativity, influencing relationships, and augmenting decision-making. We will discuss opportunities, risks, and what comes next.';
const defaultRelationships: RelationshipConfig = { hostLabel: 'Host', guestALabel: 'Guest A', guestBLabel: 'Guest B', moderation: 'moderates', respect: 'respects', disagreement: 'disagrees with' };
const durationOptions = ['2 min', '5 min', '10 min', '15 min', '20 min', '30 min', '45 min', '60 min'];
const formatOptions: Array<{ id: PodcastFormat; label: string; description: string }> = [
  { id: 'debate', label: 'Debate', description: 'Two or more opposing sides' },
  { id: 'interview', label: 'Interview', description: 'Host interviews guests' },
  { id: 'speech', label: 'Speech', description: 'Solo host presentation' },
];
const terminalStatuses = ['completed', 'complete', 'succeeded', 'success', 'done', 'failed', 'error', 'cancelled', 'canceled'];
const outputSettings = { speed: 1, pitch: 0, stability: 0.72, similarity: 0.78 };
const audioEffects = ['Compression', 'De-esser'];
const wordsPerMinute = 150;
const transcriptStorageKey = 'omnix:persistent-podcast-transcripts:v2';
const liveStreamKey = 'live-stream:buffered';

function toSpeakerDraft(profile: (typeof mockPodcastSpeakerProfiles)[number]) {
  return {
    id: profile.id,
    name: profile.name,
    role: profile.role,
    avatar: profile.avatar,
    identity: profile.identity,
    beliefs: profile.beliefs.join(', '),
    personality: profile.personality.join(', '),
    speakingStyle: profile.speakingStyle.join(', '),
    goal: profile.segmentGoals.map(({ goal }) => goal).join(' -> ') || profile.defaultGoal,
    instructions: '',
    voice: '',
  };
}

function splitTags(value: string): string[] { return String(value || '').split(',').map((tag) => tag.trim()).filter(Boolean); }
function durationMinutes(duration: string): number { return Math.max(1, Number.parseInt(duration, 10) || 1); }
function durationSeconds(duration: string): number { return durationMinutes(duration) * 60; }
function durationClock(duration: string): string { return `${durationMinutes(duration)}:00`; }
function targetWordCount(duration: string): number { return Math.max(220, Math.round(durationMinutes(duration) * wordsPerMinute)); }
function formatClock(seconds: number): string {
  const safeSeconds = Number.isFinite(seconds) && seconds > 0 ? Math.floor(seconds) : 0;
  return `${String(Math.floor(safeSeconds / 60)).padStart(2, '0')}:${String(safeSeconds % 60).padStart(2, '0')}`;
}
function isTerminal(status: unknown): boolean { return terminalStatuses.includes(String(status ?? '').toLowerCase()); }
function isFailed(status: unknown): boolean { return ['failed', 'error', 'cancelled', 'canceled'].includes(String(status ?? '').toLowerCase()); }
function firstTag(value: string): string { return splitTags(value)[0] ?? 'Neutral'; }
function speakerDisplayName(speaker: string): string { return speaker.length > 18 ? `${speaker.slice(0, 17)}…` : speaker; }
function voiceStoragePath(asset: VoiceAsset | undefined): string { return typeof (asset as any)?.storage_path === 'string' ? (asset as any).storage_path : ''; }
function voiceAssetId(asset: VoiceAsset | undefined): string { return typeof (asset as any)?.id === 'string' ? (asset as any).id : ''; }
function voiceAssetName(asset: VoiceAsset): string {
  const metadata = (asset as any).metadata ?? {};
  const metadataName = typeof metadata.profile_name === 'string' ? metadata.profile_name : typeof metadata.name === 'string' ? metadata.name : '';
  if (metadataName.trim()) return metadataName.trim();
  const source = voiceStoragePath(asset) || voiceAssetId(asset);
  return source.split(/[\\/]/).pop()?.replace(/\.[^.]+$/, '') || voiceAssetId(asset) || 'Voice';
}
function voiceOptionsFromAssets(assets: VoiceAsset[]) {
  return assets.filter((asset) => asset.type === 'voice_profile').map((asset) => ({ id: voiceStoragePath(asset) || voiceAssetId(asset), label: voiceAssetName(asset) })).filter((voice) => voice.id);
}
function jobTitle(job: { type: string; input_payload?: unknown }): string {
  const payload = job.input_payload as any;
  return payload && typeof payload.title === 'string' ? payload.title : job.type;
}
function transcriptRowsFromSegments(segments: Array<{ speaker: string; text: string }>, targetSeconds: number): TranscriptRow[] {
  if (!segments.length) return [];
  const segmentStep = Math.max(8, targetSeconds / segments.length);
  return segments.map((segment, index) => ({ timestamp: formatClock(index * segmentStep), speaker: String(segment.speaker || 'Speaker'), text: String(segment.text || '') }));
}
function transcriptRowsFromJob(job: JobRecord | undefined): TranscriptRow[] {
  const payload = job?.input_payload as any;
  const scriptSegments = Array.isArray(payload?.script_segments) ? payload.script_segments : [];
  if (!scriptSegments.length) return [];
  const targetSeconds = Number(payload?.constraints?.targetDurationSeconds || payload?.target_duration_seconds || 0);
  return transcriptRowsFromSegments(scriptSegments.map((segment) => ({ speaker: String(segment.speaker || 'Speaker'), text: String(segment.text || '') })), targetSeconds);
}
function readStoredTranscripts(): Record<string, TranscriptRow[]> {
  if (typeof window === 'undefined') return {};
  try { return JSON.parse(window.localStorage.getItem(transcriptStorageKey) || '{}') || {}; } catch { return {}; }
}
function writeStoredTranscripts(value: Record<string, TranscriptRow[]>): void {
  if (typeof window === 'undefined') return;
  try { window.localStorage.setItem(transcriptStorageKey, JSON.stringify(value)); } catch {}
}
function speakerCounts(segments: Array<{ speaker: string }>) {
  const counts: Record<string, number> = {};
  for (const segment of segments) counts[segment.speaker] = (counts[segment.speaker] ?? 0) + 1;
  return counts;
}
function podcastStages() {
  return [
    { id: 'producer_plan', label: 'Producer Plan', resource_class: 'cpu' as const, status: 'queued' as const },
    { id: 'performance_script', label: 'Performance Script', resource_class: 'cpu' as const, status: 'queued' as const },
    { id: 'speaking_turns', label: 'Speaking Turns', resource_class: 'gpu:tts' as const, status: 'queued' as const },
    { id: 'mix', label: 'Mix', resource_class: 'cpu' as const, status: 'queued' as const },
    { id: 'podcast_renderer', label: 'Podcast Renderer', resource_class: 'cpu' as const, status: 'queued' as const },
  ];
}
function stageState(status: unknown, index: number, activeIndex: number) {
  const normalized = String(status ?? '').toLowerCase();
  if (isFailed(normalized)) return 'failed';
  if (['completed', 'complete', 'succeeded', 'success', 'done'].includes(normalized)) return 'done';
  if (['running', 'in_progress', 'active', 'processing', 'leased', 'retrying', 'queued'].includes(normalized)) return 'active';
  return index === activeIndex ? 'active' : index < activeIndex ? 'done' : 'pending';
}
function buildPodcastJobPayload(args: any) {
  const counts = speakerCounts(args.segments);
  const firstVoice = args.speakers.find((speaker) => speaker.voice)?.voice || args.voiceOptions[0]?.id || null;
  const targetSeconds = durationSeconds(args.duration);
  const targetWords = targetWordCount(args.duration);
  return {
    title: args.title,
    brief: args.brief,
    format: args.format,
    audience: args.audience,
    duration_minutes: durationMinutes(args.duration),
    target_duration_seconds: targetSeconds,
    target_word_count: targetWords,
    tone: args.tone,
    language: args.language,
    generation_style: args.generationStyle,
    review_policy: args.reviewPolicy,
    renderer: 'podcast',
    text: args.segments.map((segment) => `${segment.speaker}: ${segment.text}`).join('\n'),
    provider_id: null,
    speaker: args.speakers[0]?.name || 'Host',
    voice_id: firstVoice,
    script_mode: args.segments.length > 1 ? 'multi_speaker' : 'single_speaker',
    script_speakers: Object.entries(counts).map(([name, count]) => ({ name, count })),
    script_segments: args.segments,
    character_voice_assignments: args.speakers.map((speaker, index) => ({ speaker: speaker.name, voice_id: speaker.voice || args.voiceOptions[index % Math.max(args.voiceOptions.length, 1)]?.id || null, style: firstTag(speaker.speakingStyle || speaker.personality), line_count: counts[speaker.name] ?? 0 })),
    output_settings: outputSettings,
    audio_effects: audioEffects,
    save_output: true,
    speakers: args.speakers.map((speaker) => ({
      id: speaker.id,
      name: speaker.name,
      role: speaker.role,
      identity: speaker.identity,
      beliefs: splitTags(speaker.beliefs),
      personality: splitTags(speaker.personality),
      speakingStyle: splitTags(speaker.speakingStyle),
      defaultGoal: speaker.goal,
      speakerInstructions: speaker.instructions,
      voiceMapping: { speakerId: speaker.id, voiceId: speaker.voice, voiceDisplayName: args.voiceOptions.find((voice) => voice.id === speaker.voice)?.label || speaker.voice, previewAvailable: Boolean(speaker.voice) },
    })),
    relationships: mockPodcastRelationships,
    relationship_overrides: args.relationships,
    constraints: { maxDurationSeconds: targetSeconds, targetDurationSeconds: targetSeconds, targetWordCount: targetWords, maxSpeakerTurnSeconds: Number.parseInt(args.maxTurnSeconds, 10) || 45, citationRequired: args.citationRequired === 'On', familyFriendly: args.familyFriendly === 'On', readingLevel: args.readingLevel, avoidTopics: splitTags(args.avoidTopics), requiredTopics: ['practical examples', 'risks', 'future outlook'], disallowedClaims: [], tone: args.tone, audience: args.audience, language: args.language },
  };
}
function extractPlayableOutputs(jobs: Array<JobRecord | undefined>, streamOutput?: PlayablePodcastOutput | null): PlayablePodcastOutput[] {
  const outputs: PlayablePodcastOutput[] = streamOutput ? [streamOutput] : [];
  const seen = new Set(outputs.map((output) => output.key));
  for (const job of jobs) {
    const refs = (job?.output_refs ?? []) as Array<{ data_url?: unknown; duration?: unknown; asset_id?: unknown; title?: unknown }>;
    for (const ref of refs) {
      const dataUrl = typeof ref.data_url === 'string' ? ref.data_url : '';
      if (!dataUrl.startsWith('data:audio/') && !dataUrl.startsWith('blob:')) continue;
      const title = typeof ref.title === 'string' && ref.title.trim() ? ref.title : jobTitle(job as JobRecord);
      const key = `${job?.id ?? 'job'}:${String(ref.asset_id || title || outputs.length)}`;
      if (seen.has(key)) continue;
      seen.add(key);
      outputs.push({ dataUrl, duration: Number(ref.duration || 0), jobId: job?.id || 'job', key, title });
    }
  }
  return outputs;
}
function jobErrorMessage(job: any): string { return job && isFailed(job.status) ? (typeof job.error?.message === 'string' ? `Podcast generation failed: ${job.error.message}` : 'Podcast generation failed.') : ''; }
function selectFirstJobOutput(job: JobRecord, setSelectedOutputKey: (key: string) => void): void { const output = extractPlayableOutputs([job])[0]; if (output) setSelectedOutputKey(output.key); }
function safeDownloadName(value: string): string { return value.replace(/[^A-Za-z0-9_.-]+/g, '-').replace(/^-+|-+$/g, '') || 'podcast-output'; }
function sleep(ms: number, signal?: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    const timer = window.setTimeout(resolve, ms);
    if (signal) signal.addEventListener('abort', () => { window.clearTimeout(timer); reject(new DOMException('Aborted', 'AbortError')); }, { once: true });
  });
}
function decodeBase64ToBytes(value: string): Uint8Array { const binary = atob(value); const bytes = new Uint8Array(binary.length); for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index); return bytes; }
function audioDataUrlToBase64(dataUrl: string): string { return dataUrl.includes(',') ? dataUrl.split(',').pop() || '' : dataUrl; }
function decodeBase64Pcm16(value: string): Int16Array { return new Int16Array(decodeBase64ToBytes(value).buffer); }
function decodeBase64WavPcm16(value: string): { pcm: Int16Array; sampleRate: number } | null {
  const bytes = decodeBase64ToBytes(value);
  if (bytes.length < 44) return null;
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  if (String.fromCharCode(bytes[0], bytes[1], bytes[2], bytes[3]) !== 'RIFF') return null;
  const sampleRate = view.getUint32(24, true) || 24000;
  let offset = 12;
  while (offset + 8 <= bytes.length) {
    const chunkId = String.fromCharCode(bytes[offset], bytes[offset + 1], bytes[offset + 2], bytes[offset + 3]);
    const chunkSize = view.getUint32(offset + 4, true);
    if (chunkId === 'data') {
      const dataStart = offset + 8;
      const dataEnd = Math.min(bytes.length, dataStart + chunkSize);
      const dataBytes = bytes.slice(dataStart, dataEnd);
      return { pcm: new Int16Array(dataBytes.buffer), sampleRate };
    }
    offset += 8 + chunkSize + (chunkSize % 2);
  }
  return null;
}
function buildWavDataUrl(chunks: Int16Array[], sampleRate: number): { dataUrl: string; duration: number } | null {
  const totalSamples = chunks.reduce((sum, chunk) => sum + chunk.length, 0);
  if (!totalSamples) return null;
  const pcm = new Int16Array(totalSamples);
  let offset = 0;
  for (const chunk of chunks) { pcm.set(chunk, offset); offset += chunk.length; }
  const dataSize = pcm.length * 2;
  const buffer = new ArrayBuffer(44 + dataSize);
  const view = new DataView(buffer);
  const writeString = (at: number, value: string) => { for (let index = 0; index < value.length; index += 1) view.setUint8(at + index, value.charCodeAt(index)); };
  writeString(0, 'RIFF'); view.setUint32(4, 36 + dataSize, true); writeString(8, 'WAVE'); writeString(12, 'fmt '); view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true); view.setUint32(24, sampleRate, true); view.setUint32(28, sampleRate * 2, true); view.setUint16(32, 2, true); view.setUint16(34, 16, true); writeString(36, 'data'); view.setUint32(40, dataSize, true);
  for (let index = 0; index < pcm.length; index += 1) view.setInt16(44 + index * 2, pcm[index], true);
  const bytes = new Uint8Array(buffer);
  let binary = '';
  for (let index = 0; index < bytes.length; index += 0x8000) binary += String.fromCharCode(...bytes.subarray(index, index + 0x8000));
  return { dataUrl: `data:audio/wav;base64,${btoa(binary)}`, duration: pcm.length / sampleRate };
}
function buildSingleSpeakerJob(segment: { speaker: string; text: string }, speaker: SpeakerDraft | undefined, title: string) {
  const speakerName = speaker?.name || segment.speaker;
  return { module: 'podcast', type: 'tts.synthesize', resource_class: 'gpu:tts', priority: 1, input_payload: { text: segment.text, title: `${speakerName} live preview`, provider_id: null, speaker: speakerName, voice_id: speaker?.voice || null, script_mode: 'single_speaker', script_speakers: [{ name: speakerName, count: 1 }], script_segments: [{ index: 0, speaker: speakerName, text: segment.text }], character_voice_assignments: [{ speaker: speakerName, voice_id: speaker?.voice || null, style: firstTag(speaker?.speakingStyle || speaker?.personality || ''), line_count: 1 }], output_settings: outputSettings, audio_effects: audioEffects, save_output: true, source: 'podcast_live_preview', podcast_title: title }, stages: [{ id: 'preview_voice', label: 'Voice Preview', resource_class: 'gpu:tts', status: 'queued' }] };
}
async function waitForPlayableJob(job: JobRecord, signal: AbortSignal): Promise<PlayablePodcastOutput> {
  let current = job;
  for (let attempt = 0; attempt < 180; attempt += 1) {
    if (signal.aborted) throw new DOMException('Aborted', 'AbortError');
    const output = extractPlayableOutputs([current])[0];
    if (output) return output;
    if (isFailed(current.status)) throw new Error(jobErrorMessage(current) || 'TTS job failed.');
    await sleep(1000, signal);
    current = await omnixApiClient.getJob(current.id);
  }
  throw new Error('Timed out waiting for generated audio.');
}
async function generateVoicePreviewTake(segment: { speaker: string; text: string }, speaker: SpeakerDraft | undefined, title: string, abortSignal: AbortSignal) {
  const job = await omnixApiClient.createJob(buildSingleSpeakerJob(segment, speaker, title));
  const output = await waitForPlayableJob(job, abortSignal);
  const base64Audio = audioDataUrlToBase64(output.dataUrl);
  if (!base64Audio) throw new Error('TTS job completed without audio data.');
  return { audioBase64: base64Audio, sampleRate: 24000, jobId: output.jobId, duration: output.duration };
}
async function streamPodcastSegments(args: { abortSignal: AbortSignal; onBuffered: (output: PlayablePodcastOutput) => void; onChunk: (message: string) => void; onComplete: (output: PlayablePodcastOutput) => void; onFallback: (message: string) => void; onProgressStage: (stage: number) => void; segments: Array<{ speaker: string; text: string }>; speakers: SpeakerDraft[]; title: string }) {
  if (typeof window === 'undefined' || typeof atob === 'undefined') return false;
  const pcmChunks: Int16Array[] = [];
  let sampleRate = 24000;
  for (let index = 0; index < args.segments.length; index += 1) {
    if (args.abortSignal.aborted) return false;
    const segment = args.segments[index];
    const speaker = args.speakers.find((entry) => entry.name === segment.speaker) ?? args.speakers[index % Math.max(args.speakers.length, 1)];
    args.onProgressStage(2);
    args.onChunk(`Queueing speaking turn ${index + 1}/${args.segments.length}: ${segment.speaker}`);
    try {
      const result = await generateVoicePreviewTake(segment, speaker, args.title || 'Podcast', args.abortSignal);
      const decoded = decodeBase64WavPcm16(result.audioBase64) ?? { pcm: decodeBase64Pcm16(result.audioBase64), sampleRate: result.sampleRate };
      sampleRate = decoded.sampleRate || sampleRate || 24000;
      pcmChunks.push(decoded.pcm);
      const wav = buildWavDataUrl(pcmChunks, sampleRate);
      if (wav && !args.abortSignal.aborted) args.onBuffered({ dataUrl: wav.dataUrl, duration: wav.duration, jobId: 'live-stream', key: liveStreamKey, title: `${args.title || 'Podcast'} live preview` });
    } catch (error) {
      if (!args.abortSignal.aborted) args.onFallback(`Live voice preview stopped: ${error instanceof Error ? error.message : 'unknown error'}. Final podcast job will continue.`);
      return false;
    }
  }
  const wav = buildWavDataUrl(pcmChunks, sampleRate);
  if (wav && !args.abortSignal.aborted) { args.onProgressStage(3); args.onComplete({ dataUrl: wav.dataUrl, duration: wav.duration, jobId: 'live-stream', key: liveStreamKey, title: `${args.title || 'Podcast'} live preview` }); return true; }
  return false;
}

export function PodcastWorkspace({ module }: { module: OmnixModuleDefinition }) {
  const queryClient = useQueryClient();
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const streamAbortRef = useRef<AbortController | null>(null);
  const userWantsStreamPlaybackRef = useRef(false);
  const pendingStreamResumeRef = useRef<{ time: number; shouldPlay: boolean } | null>(null);
  const jobsQuery = useQuery({ queryKey: ['platform', 'jobs'], queryFn: () => omnixApiClient.listJobs(), refetchInterval: 1500, refetchOnWindowFocus: true });
  const assetsQuery = useQuery({ queryKey: ['platform', 'assets'], queryFn: () => omnixApiClient.listAssets(), refetchInterval: 5000 });
  const [title, setTitle] = useState(defaultTitle);
  const [brief, setBrief] = useState(defaultBrief);
  const [audience, setAudience] = useState('Software Engineers');
  const [duration, setDuration] = useState('20 min');
  const [tone, setTone] = useState('Professional');
  const [language, setLanguage] = useState('English (US)');
  const [format, setFormat] = useState<PodcastFormat>('debate');
  const [generationStyle, setGenerationStyle] = useState('automatic');
  const [manualReviewStops, setManualReviewStops] = useState<string[]>([]);
  const [speakers, setSpeakers] = useState(() => mockPodcastSpeakerProfiles.map(toSpeakerDraft));
  const [transcript, setTranscript] = useState<TranscriptRow[]>([]);
  const [storedTranscripts, setStoredTranscripts] = useState<Record<string, TranscriptRow[]>>(() => readStoredTranscripts());
  const [directorNote, setDirectorNote] = useState('No live production is running. Configure the episode, then press Generate live podcast.');
  const [directorCollapsed, setDirectorCollapsed] = useState(false);
  const [speakerMenuId, setSpeakerMenuId] = useState('');
  const [showAllRecentJobs, setShowAllRecentJobs] = useState(false);
  const [collapsedPanels, setCollapsedPanels] = useState<Record<SidebarPanel, boolean>>({ quality: false, health: false, recent: false });
  const [liveCommand, setLiveCommand] = useState('');
  const [playbackRate, setPlaybackRate] = useState('1.0x');
  const [playbackDuration, setPlaybackDuration] = useState(0);
  const [selectedOutputKey, setSelectedOutputKey] = useState('');
  const [streamOutput, setStreamOutput] = useState<PlayablePodcastOutput | null>(null);
  const [streamStatus, setStreamStatus] = useState('');
  const [liveStreamActive, setLiveStreamActive] = useState(false);
  const [liveStreamStage, setLiveStreamStage] = useState(-1);
  const [citationRequired, setCitationRequired] = useState('On');
  const [familyFriendly, setFamilyFriendly] = useState('On');
  const [readingLevel, setReadingLevel] = useState('Grade 8');
  const [maxTurnSeconds, setMaxTurnSeconds] = useState('45');
  const [avoidTopics, setAvoidTopics] = useState('Politics');
  const [relationships, setRelationships] = useState<RelationshipConfig>(defaultRelationships);
  const [actionMessage, setActionMessage] = useState('Ready for automatic production.');
  const voiceOptions = useMemo(() => voiceOptionsFromAssets(assetsQuery.data?.assets ?? []), [assetsQuery.data?.assets]);
  const reviewPolicy = buildReviewPolicy(generationStyle, generationStyle === 'guided' ? manualReviewStops : []);

  useEffect(() => {
    if (!voiceOptions.length) return;
    setSpeakers((current) => current.map((speaker, index) => speaker.voice && voiceOptions.some((voice) => voice.id === speaker.voice) ? speaker : { ...speaker, voice: voiceOptions[index % voiceOptions.length].id }));
  }, [voiceOptions.map((voice) => voice.id).join('|')]);

  const createJobMutation = useMutation({
    mutationFn: (segments: Array<{ index: number; speaker: string; text: string }>) => omnixApiClient.createJob({ module: 'podcast', type: 'tts.multi_speaker_synthesize', resource_class: 'gpu:tts', priority: 0, input_payload: buildPodcastJobPayload({ title, brief, format, audience, duration, tone, language, generationStyle, reviewPolicy, speakers, voiceOptions, segments, citationRequired, familyFriendly, readingLevel, maxTurnSeconds, avoidTopics, relationships }), stages: podcastStages() }),
    onMutate: () => { setDirectorNote(streamOutput ? 'Live preview complete. Rendering final persisted podcast output.' : 'Director queued final podcast rendering.'); setStreamStatus((current) => current || 'Final podcast render queued.'); setActionMessage('Final podcast render queued.'); },
    onSuccess: async (job) => {
      selectFirstJobOutput(job, setSelectedOutputKey);
      const rows = transcriptRowsFromJob(job);
      if (rows.length) { setTranscript(rows); setStoredTranscripts((current) => { const next = { ...current, [job.id]: rows }; writeStoredTranscripts(next); return next; }); }
      if (isFailed(job.status)) { setDirectorNote(jobErrorMessage(job)); setActionMessage(jobErrorMessage(job)); } else { setDirectorNote(`Director queued ${job.type}. Podcast audio is using Voice Library assignments.`); setActionMessage(extractPlayableOutputs([job]).length ? `Podcast audio ready: ${job.id}` : `Podcast production queued: ${job.id}`); }
      await Promise.all([queryClient.invalidateQueries({ queryKey: ['platform', 'jobs'] }), queryClient.invalidateQueries({ queryKey: ['platform', 'assets'] })]);
    },
  });
  const previewVoiceMutation = useMutation({
    mutationFn: (speaker: SpeakerDraft) => omnixApiClient.createJob(buildSingleSpeakerJob({ speaker: speaker.name, text: `This is a preview of ${speaker.name} for ${title}.` }, speaker, title)),
    onSuccess: async (job) => { selectFirstJobOutput(job, setSelectedOutputKey); setActionMessage(isFailed(job.status) ? jobErrorMessage(job) : `Voice preview ${extractPlayableOutputs([job]).length ? 'ready' : 'queued'}: ${job.id}`); await Promise.all([queryClient.invalidateQueries({ queryKey: ['platform', 'jobs'] }), queryClient.invalidateQueries({ queryKey: ['platform', 'assets'] })]); },
  });

  const podcastJobs = jobsQuery.data?.jobs.filter((job) => job.module === 'podcast') ?? [];
  const activeJob = podcastJobs.find((job) => !isTerminal(job.status));
  const connectedJob = createJobMutation.data ?? previewVoiceMutation.data ?? activeJob ?? podcastJobs[0];
  const playableOutputs = useMemo(() => extractPlayableOutputs([createJobMutation.data, previewVoiceMutation.data, ...podcastJobs], streamOutput), [createJobMutation.data, podcastJobs, previewVoiceMutation.data, streamOutput]);
  const selectedOutput = selectedOutputKey ? playableOutputs.find((output) => output.key === selectedOutputKey) ?? null : playableOutputs[0] ?? null;
  const currentOutput = selectedOutputKey === '__new__' ? null : selectedOutputKey === '__pending__' ? streamOutput : selectedOutput;
  const persistedTranscript = connectedJob?.id ? storedTranscripts[connectedJob.id] ?? [] : [];
  const jobTranscript = transcriptRowsFromJob(connectedJob);
  const transcriptRows = transcript.length ? transcript : persistedTranscript.length ? persistedTranscript : jobTranscript;
  const liveActive = liveStreamActive || createJobMutation.isPending || previewVoiceMutation.isPending || Boolean(connectedJob && !isTerminal(connectedJob.status));
  const liveStatus = liveStreamActive ? 'STREAMING' : createJobMutation.isPending || previewVoiceMutation.isPending ? 'QUEUEING' : connectedJob ? String(connectedJob.status).toUpperCase() : 'IDLE';
  const jobStages = connectedJob?.stages ?? [];
  const plannedStages = podcastStages();
  const firstIncomplete = jobStages.findIndex((stage) => !['completed', 'done', 'success'].includes(String(stage.status).toLowerCase()));
  const activeStage = liveStreamActive ? liveStreamStage : createJobMutation.isPending || previewVoiceMutation.isPending ? 0 : connectedJob ? (firstIncomplete >= 0 ? firstIncomplete : jobStages.length - 1) : -1;
  const stages = liveStreamActive ? plannedStages.map((stage, index) => ({ ...stage, state: index < liveStreamStage ? 'done' : index === liveStreamStage ? 'active' : 'pending' })) : jobStages.length ? jobStages.map((stage, index) => ({ id: stage.id, label: stage.label, state: stageState(stage.status, index, activeStage) })) : plannedStages.map((stage) => ({ ...stage, state: 'pending' }));
  const failed = !liveStreamActive && isFailed(connectedJob?.status);
  const recentJobs = podcastJobs.length ? podcastJobs.slice(0, showAllRecentJobs ? 12 : 3).map((job) => ({ id: job.id, name: jobTitle(job), status: job.status, duration })) : mockRecentPodcastJobs.map((job) => ({ ...job, id: job.name }));
  const showBriefError = brief.trim().length === 0 && createJobMutation.isIdle === false;

  useEffect(() => {
    if (!selectedOutputKey && playableOutputs.length > 0) setSelectedOutputKey(playableOutputs[0].key);
    if (selectedOutputKey === '__pending__') { const newOutput = createJobMutation.data?.id ? playableOutputs.find((output) => output.jobId === createJobMutation.data?.id) : playableOutputs.find((output) => output.jobId === 'live-stream'); if (newOutput) setSelectedOutputKey(newOutput.key); }
  }, [createJobMutation.data?.id, playableOutputs, selectedOutputKey]);
  useEffect(() => () => streamAbortRef.current?.abort(), []);
  useEffect(() => {
    const player = audioRef.current;
    setPlaybackDuration(currentOutput?.duration ?? 0);
    if (!player) return;
    const pending = pendingStreamResumeRef.current;
    pendingStreamResumeRef.current = null;
    player.load();
    if (!pending) return;
    let restored = false;
    const restore = () => {
      if (restored) return;
      restored = true;
      const durationLimit = currentOutput?.duration && currentOutput.duration > 0 ? currentOutput.duration : Number.POSITIVE_INFINITY;
      const targetTime = Math.max(0, Math.min(pending.time, Math.max(0, durationLimit - 0.05)));
      try { if (Number.isFinite(targetTime)) player.currentTime = targetTime; } catch {}
      if (pending.shouldPlay && currentOutput?.dataUrl) player.play().catch(() => undefined);
    };
    player.addEventListener('loadedmetadata', restore, { once: true });
    window.setTimeout(restore, 0);
    return () => player.removeEventListener('loadedmetadata', restore);
  }, [currentOutput?.key, currentOutput?.dataUrl]);

  function bufferStreamOutput(output: PlayablePodcastOutput) {
    const player = audioRef.current;
    const currentTime = player?.currentTime ?? 0;
    const shouldResume = liveStreamActive && (userWantsStreamPlaybackRef.current || Boolean(player && !player.paused && !player.ended));
    pendingStreamResumeRef.current = { time: currentTime, shouldPlay: shouldResume };
    setStreamOutput(output);
    setSelectedOutputKey((current) => current === '__pending__' || current === liveStreamKey ? output.key : current);
    setPlaybackDuration(output.duration);
  }
  function startGeneration() {
    if (!brief.trim()) return;
    const segments = buildConversationalPodcastSegments(title, brief, audience, speakers, duration);
    streamAbortRef.current?.abort();
    audioRef.current?.pause();
    userWantsStreamPlaybackRef.current = false;
    const abortController = new AbortController();
    streamAbortRef.current = abortController;
    setStreamOutput(null); setSelectedOutputKey('__pending__'); setPlaybackDuration(0); setLiveStreamActive(true); setLiveStreamStage(0); setTranscript(transcriptRowsFromSegments(segments, durationSeconds(duration)));
    setDirectorNote('Director started live preview. Voice turns are queued through the platform job API, so the app no longer calls missing legacy /api/voice_studio or /api/tts routes.');
    setStreamStatus('Preparing live voice preview jobs...'); setActionMessage('Live voice preview is starting...');
    void (async () => {
      const streamed = await streamPodcastSegments({ abortSignal: abortController.signal, segments, speakers, title: title || 'Podcast', onBuffered: bufferStreamOutput, onChunk: (message) => { setStreamStatus(message); setActionMessage(message); }, onFallback: (message) => { setStreamStatus(message); setActionMessage(message); }, onProgressStage: setLiveStreamStage, onComplete: (output) => { bufferStreamOutput(output); setStreamStatus('Live preview complete. Final persisted podcast output is queued next.'); } });
      if (abortController.signal.aborted) return;
      setLiveStreamActive(false); setLiveStreamStage(streamed ? 3 : -1); createJobMutation.mutate(segments);
    })();
  }
  function stopLiveStream() { streamAbortRef.current?.abort(); streamAbortRef.current = null; userWantsStreamPlaybackRef.current = false; setLiveStreamActive(false); setLiveStreamStage(-1); audioRef.current?.pause(); setStreamStatus(streamOutput ? 'Live preview stopped. Buffered audio remains in the player.' : 'Live preview stopped.'); setActionMessage('Live preview stopped.'); }
  function seekAudio(deltaSeconds: number) { const player = audioRef.current; if (!player) return; const maxTime = Number.isFinite(player.duration) ? player.duration : currentOutput?.duration ?? player.currentTime; player.currentTime = Math.max(0, Math.min(maxTime, player.currentTime + deltaSeconds)); }
  function toggleReviewStop(stopId: string) { setManualReviewStops((current) => current.includes(stopId) ? current.filter((id) => id !== stopId) : [...current, stopId]); }
  function updateSpeaker(id: string, field: string, value: string) { setSpeakers((current) => current.map((speaker) => speaker.id === id ? { ...speaker, [field]: value } : speaker)); }
  function addParticipant() { const next = speakers.length + 1; setSpeakers((current) => [...current, { id: `guest_${next}`, name: `Guest ${next}`, role: 'Guest Analyst', avatar: `G${next}`, identity: 'Guest Analyst', beliefs: '', personality: '', speakingStyle: '', goal: '', instructions: '', voice: voiceOptions[0]?.id ?? '' }]); setActionMessage('Added participant.'); }
  function removeParticipant(id: string) { if (speakers.length <= 1) { setActionMessage('Keep at least one participant.'); return; } setSpeakers((current) => current.filter((speaker) => speaker.id !== id)); setSpeakerMenuId(''); setActionMessage('Removed participant.'); }
  function duplicateParticipant(speaker: SpeakerDraft) { setSpeakers((current) => [...current, { ...speaker, id: `${speaker.id}_copy_${current.length + 1}`, name: `${speaker.name} Copy` }]); setSpeakerMenuId(''); setActionMessage(`Duplicated ${speaker.name}.`); }
  function submitLiveCommand() { const command = liveCommand.trim(); if (!command) return; if (!liveActive) { setActionMessage('Live edits apply during an active production run.'); return; } setDirectorNote(`Director applied live note: ${command}`); setTranscript((lines) => [...lines, { timestamp: formatClock(lines.length * 15), speaker: 'Director', text: command }]); setLiveCommand(''); }
  function updateRelationship(field: keyof RelationshipConfig, value: string) { setRelationships((current) => ({ ...current, [field]: value })); }
  function toggleSidebarPanel(panel: SidebarPanel) { setCollapsedPanels((current) => ({ ...current, [panel]: !current[panel] })); }
  function resetPodcast() { streamAbortRef.current?.abort(); audioRef.current?.pause(); userWantsStreamPlaybackRef.current = false; setLiveStreamActive(false); setLiveStreamStage(-1); setTitle(''); setBrief(''); setAudience('Software Engineers'); setDuration('5 min'); setTone('Professional'); setLanguage('English (US)'); setFormat('debate'); setGenerationStyle('automatic'); setManualReviewStops([]); setTranscript([]); setStreamOutput(null); setStreamStatus(''); setDirectorNote('New podcast request cleared. Add a title and brief, then generate.'); setSelectedOutputKey('__new__'); setPlaybackDuration(0); setActionMessage('New podcast ready.'); }
  function selectRecentJob(jobId: string) { const output = playableOutputs.find((entry) => entry.jobId === jobId); const job = podcastJobs.find((entry) => entry.id === jobId); const rows = storedTranscripts[jobId] ?? transcriptRowsFromJob(job); if (rows.length) setTranscript(rows); if (output) { setSelectedOutputKey(output.key); setActionMessage(`Selected audio output: ${output.title}.`); return; } setActionMessage(`Selected job ${jobId}; no playable audio output is attached yet.`); }
  function downloadCurrentOutput(label = 'Podcast audio') { if (!currentOutput || typeof document === 'undefined') { setActionMessage('Generate podcast audio before downloading.'); return; } const link = document.createElement('a'); link.href = currentOutput.dataUrl; link.download = `${safeDownloadName(currentOutput.title || title)}.wav`; link.click(); setActionMessage(`${label}: download started.`); }
  async function copyEpisodeLink() { const link = typeof window !== 'undefined' ? `${window.location.href.split('#')[0]}#${connectedJob?.id ?? 'podcast'}` : connectedJob?.id ?? 'podcast'; try { await navigator.clipboard?.writeText(link); setActionMessage('Podcast link copied.'); } catch { setActionMessage(`Podcast link: ${link}`); } }
  function handleAudioPlay() { if (liveStreamActive || currentOutput?.jobId === 'live-stream') userWantsStreamPlaybackRef.current = true; }
  function handleAudioPause(event) { if (!liveStreamActive || !event.currentTarget.ended) userWantsStreamPlaybackRef.current = false; }
  function handleAudioEnded() { if (liveStreamActive) { userWantsStreamPlaybackRef.current = true; setStreamStatus('Waiting for the next generated speaking turn...'); } else { userWantsStreamPlaybackRef.current = false; } }

  return (
    <WorkspacePanel className="podcast-workspace-panel">
      <div className="podcast-studio-shell">
        <header className="podcast-studio-header"><div><p className="eyebrow">Conversation engine</p><h2 id="module-title">{module.label}</h2><p>Create a podcast from a real speaker-tagged conversation, Voice Library assignments, and platform TTS jobs.</p></div><code>/podcast-renderer</code></header>
        <div className="podcast-studio-grid">
          <section className="podcast-studio-stack">
            <article className="podcast-card episode-setup-card"><div className="card-heading-row"><h3>1. Episode setup</h3><button className="ghost-button compact" type="button" onClick={resetPodcast}>New podcast</button></div><div className="episode-setup-grid"><div className="podcast-field-stack"><label>Topic / Episode title<input value={title} onChange={(event) => setTitle(event.target.value)} /></label><label>Episode brief<textarea rows={5} value={brief} onChange={(event) => setBrief(event.target.value)} /><small>{brief.length}/2000</small></label><label>Audience<select value={audience} onChange={(event) => setAudience(event.target.value)}><option>Software Engineers</option><option>General Public</option><option>Executives</option><option>Students</option><option>Experts</option></select></label></div><div className="podcast-config-stack"><span className="podcast-label">Podcast format</span><div className="format-card-grid">{formatOptions.map((option) => <button key={option.id} type="button" className={option.id === format ? 'selected' : undefined} onClick={() => setFormat(option.id)}><strong>{option.label}</strong><small>{option.description}</small></button>)}</div><div className="podcast-select-grid"><label>Duration<select value={duration} onChange={(event) => setDuration(event.target.value)}>{durationOptions.map((option) => <option key={option}>{option}</option>)}</select></label><label>Tone<select value={tone} onChange={(event) => setTone(event.target.value)}><option>Professional</option><option>Conversational</option><option>Humorous</option></select></label><label>Language<select value={language} onChange={(event) => setLanguage(event.target.value)}><option>English (US)</option><option>English (UK)</option></select></label></div><div className="generation-style-panel"><span className="podcast-label">Generation Style</span>{generationStyleOptions.map((option) => <label key={option.id} className={generationStyle === option.id ? 'generation-style selected' : 'generation-style'}><input type="radio" checked={generationStyle === option.id} onChange={() => setGenerationStyle(option.id)} /><span><strong>{option.label}</strong><small>{option.description}</small></span></label>)}<div className="review-stop-row">{reviewStopOptions.map((option) => <label key={option.id}><input type="checkbox" disabled={generationStyle !== 'guided'} checked={manualReviewStops.includes(option.id)} onChange={() => toggleReviewStop(option.id)} />{option.label}</label>)}</div></div></div></div></article>
            <article className="podcast-card"><div className="card-heading-row"><h3>2. Participants and voice casting</h3><small>{voiceOptions.length ? `Loaded ${voiceOptions.length} Voice Library voice${voiceOptions.length === 1 ? '' : 's'}` : 'No Voice Library voices found'}</small></div><div className="speaker-table editable-speaker-table"><div className="speaker-row speaker-header"><span>Speaker</span><span>Identity</span><span>Voice</span><span>Beliefs</span><span>Personality</span><span>Speaking style</span><span>Goal this episode</span><span>Instructions</span><span>Actions</span></div>{speakers.map((speaker) => <div className="speaker-row editable-speaker-row" key={speaker.id}><span className="speaker-cell-main"><b className={`speaker-avatar ${speaker.id}`}>{speaker.avatar}</b><span><input value={speaker.name} onChange={(event) => updateSpeaker(speaker.id, 'name', event.target.value)} /><input value={speaker.role} onChange={(event) => updateSpeaker(speaker.id, 'role', event.target.value)} /></span></span><span><input value={speaker.identity} onChange={(event) => updateSpeaker(speaker.id, 'identity', event.target.value)} /></span><span><select aria-label={`${speaker.name} voice`} value={speaker.voice} onChange={(event) => updateSpeaker(speaker.id, 'voice', event.target.value)}>{voiceOptions.map((voice) => <option key={voice.id} value={voice.id}>{voice.label}</option>)}{!voiceOptions.length ? <option value="">No cloned voices</option> : null}</select></span><span><textarea rows={2} value={speaker.beliefs} onChange={(event) => updateSpeaker(speaker.id, 'beliefs', event.target.value)} /></span><span><textarea rows={2} value={speaker.personality} onChange={(event) => updateSpeaker(speaker.id, 'personality', event.target.value)} /></span><span><textarea rows={2} value={speaker.speakingStyle} onChange={(event) => updateSpeaker(speaker.id, 'speakingStyle', event.target.value)} /></span><span><textarea rows={2} value={speaker.goal} onChange={(event) => updateSpeaker(speaker.id, 'goal', event.target.value)} /></span><span><textarea rows={2} value={speaker.instructions} onChange={(event) => updateSpeaker(speaker.id, 'instructions', event.target.value)} placeholder="Extra personality, pacing, conflict, or behavior notes" /></span><span className="speaker-preview speaker-actions"><button type="button" onClick={() => previewVoiceMutation.mutate(speaker)} disabled={!speaker.voice || previewVoiceMutation.isPending}>Preview</button><button type="button" onClick={() => removeParticipant(speaker.id)}>Remove</button><button type="button" onClick={() => setSpeakerMenuId((current) => current === speaker.id ? '' : speaker.id)}>More</button>{speakerMenuId === speaker.id ? <div className="speaker-menu"><button type="button" onClick={() => duplicateParticipant(speaker)}>Duplicate participant</button><button type="button" onClick={() => updateSpeaker(speaker.id, 'instructions', '')}>Clear instructions</button></div> : null}</span></div>)}</div><button className="ghost-button" type="button" onClick={addParticipant}>+ Add participant</button></article>
            <article className="podcast-card relationship-card"><h3>3. Relationships and constraints</h3><div className="relationship-layout relationship-layout-clear"><div className="relationship-map relationship-map-clear"><div className="relationship-map-title"><b>Panel relationships</b><small>Directional links for the current episode</small></div><div className="relationship-node-card host"><b>H</b><span>{relationships.hostLabel}</span><small>moderator</small></div><div className="relationship-node-card guest-a"><b>GA</b><span>{relationships.guestALabel}</span><small>guest A</small></div><div className="relationship-node-card guest-b"><b>GB</b><span>{relationships.guestBLabel}</span><small>guest B</small></div><div className="relationship-edge-list"><p><strong>{relationships.hostLabel}</strong><em>{relationships.moderation}</em><strong>{relationships.guestALabel}</strong></p><p><strong>{relationships.guestALabel}</strong><em>{relationships.respect}</em><strong>{relationships.guestBLabel}</strong></p><p><strong>{relationships.guestBLabel}</strong><em>{relationships.disagreement}</em><strong>{relationships.hostLabel}</strong></p></div></div><div className="relationship-config-grid"><label>Host label<input value={relationships.hostLabel} onChange={(event) => updateRelationship('hostLabel', event.target.value)} /></label><label>Guest A label<input value={relationships.guestALabel} onChange={(event) => updateRelationship('guestALabel', event.target.value)} /></label><label>Guest B label<input value={relationships.guestBLabel} onChange={(event) => updateRelationship('guestBLabel', event.target.value)} /></label><label>Moderator relation<input value={relationships.moderation} onChange={(event) => updateRelationship('moderation', event.target.value)} /></label><label>Respect relation<input value={relationships.respect} onChange={(event) => updateRelationship('respect', event.target.value)} /></label><label>Conflict relation<input value={relationships.disagreement} onChange={(event) => updateRelationship('disagreement', event.target.value)} /></label></div><div className="constraint-grid editable"><label><small>Max duration</small><strong>{durationClock(duration)}</strong></label><label><small>Citation required</small><select value={citationRequired} onChange={(event) => setCitationRequired(event.target.value)}><option>On</option><option>Off</option></select></label><label><small>Family friendly</small><select value={familyFriendly} onChange={(event) => setFamilyFriendly(event.target.value)}><option>On</option><option>Off</option></select></label><label><small>Reading level</small><select value={readingLevel} onChange={(event) => setReadingLevel(event.target.value)}><option>Grade 8</option><option>Grade 10</option><option>Expert</option></select></label><label><small>Max turn</small><select value={maxTurnSeconds} onChange={(event) => setMaxTurnSeconds(event.target.value)}><option value="20">20 sec</option><option value="45">45 sec</option><option value="60">60 sec</option><option value="90">90 sec</option></select></label><label><small>Avoid topics</small><input value={avoidTopics} onChange={(event) => setAvoidTopics(event.target.value)} /></label></div></div></article>
            <form className="episode-action-row" onSubmit={(event) => { event.preventDefault(); startGeneration(); }}><button className="ghost-button" type="button" onClick={resetPodcast}>New podcast</button><button className="podcast-generate-button" type="submit" disabled={liveStreamActive || createJobMutation.isPending}>Generate live podcast</button></form><FeatureValidationMessage show={showBriefError} message="Enter an episode brief before generating a podcast." /><FeatureSubmitFeedback error={createJobMutation.error} errorPrefix="Podcast request" isError={createJobMutation.isError} isPending={createJobMutation.isPending} jobId={createJobMutation.data?.status === 'failed' ? undefined : createJobMutation.data?.id} pendingMessage="Starting voice production" successPrefix="Podcast production queued" />
          </section>
          <section className="podcast-live-column"><article className={`podcast-card live-production-card ${liveActive ? 'streaming' : 'idle'}`}><div className="card-heading-row"><h3>Live production</h3><span className="auto-badge">{liveStatus}</span></div><div className="stage-rail">{stages.map((stage, index) => <span key={`${stage.id}-${stage.label}`} className={stage.state}>{stage.state === 'done' ? 'OK' : stage.state === 'failed' ? '!' : index + 1}<small>{stage.label}</small></span>)}</div><div className="director-note"><b>Director</b><span>{directorCollapsed ? 'Director note collapsed.' : failed ? (jobErrorMessage(connectedJob) || 'Last podcast job failed. Fix the request or regenerate to start a new live production run.') : directorNote}</span><button type="button" onClick={() => setDirectorCollapsed((value) => !value)}>{directorCollapsed ? 'Expand' : 'Collapse'}</button></div><div className={`waveform ${liveActive ? 'streaming' : 'idle'}`} aria-hidden="true">{Array.from({ length: 64 }, (_, index) => <i key={index} style={{ height: `${18 + ((index * 17 + transcriptRows.length * 5) % 42)}px` }} />)}</div><section className="live-transcript-section"><div className="card-heading-row"><h4>Transcript</h4><small>{transcriptRows.length ? `${transcriptRows.length} line${transcriptRows.length === 1 ? '' : 's'}` : 'Waiting for script'}</small></div><div className="live-transcript">{transcriptRows.length ? transcriptRows.map((line, index) => <p key={`${line.timestamp}-${line.speaker}-${index}`}><time>{line.timestamp}</time><b title={line.speaker}>{speakerDisplayName(line.speaker)}</b><span>{line.text}</span></p>) : <div className="live-empty-state"><strong>{failed ? 'Production failed' : 'No live transcript yet'}</strong><span>{failed ? (jobErrorMessage(connectedJob) || 'The last podcast job reported a failure.') : 'Press Generate live podcast to start live production events.'}</span></div>}</div></section><div className="podcast-audio-player" aria-label="Podcast audio player"><div className="audio-player-heading"><span>{currentOutput ? currentOutput.title : streamStatus || 'No podcast audio yet'}</span><small>{currentOutput ? 'AUDIO READY' : streamStatus ? 'LIVE PREVIEW' : 'Generate a completed podcast to enable playback'}</small></div>{streamStatus && !currentOutput ? <p className="streaming-note">{streamStatus}</p> : null}<audio ref={audioRef} src={currentOutput?.dataUrl ?? undefined} controls preload="auto" onPlay={handleAudioPlay} onPause={handleAudioPause} onEnded={handleAudioEnded} onLoadedMetadata={(event) => setPlaybackDuration(event.currentTarget.duration || currentOutput?.duration || 0)} onCanPlay={() => currentOutput && setActionMessage(`Audio available: ${currentOutput.title}`)} onError={() => setActionMessage('The generated audio could not be loaded by the browser.')} /><div className="audio-toolbar"><label>Playback speed<select value={playbackRate} onChange={(event) => { setPlaybackRate(event.target.value); if (audioRef.current) audioRef.current.playbackRate = Number.parseFloat(event.target.value) || 1; }}><option>0.8x</option><option>1.0x</option><option>1.25x</option></select></label><div className="audio-transport-buttons"><button type="button" disabled={!currentOutput} onClick={() => seekAudio(-10)}>Back 10s</button><button type="button" disabled={!currentOutput} onClick={() => seekAudio(10)}>Forward 10s</button><button type="button" disabled={!liveStreamActive && !streamOutput} onClick={stopLiveStream}>Stop preview</button></div><small>{currentOutput ? `${formatClock(playbackDuration || currentOutput.duration)} buffered` : streamStatus ? 'Voice turns buffer into the player while generating' : 'No audio loaded'}</small></div></div><form className="live-command" onSubmit={(event) => { event.preventDefault(); submitLiveCommand(); }}><input value={liveCommand} disabled={!liveActive} onChange={(event) => setLiveCommand(event.target.value)} placeholder={liveActive ? 'Make Guest B more skeptical' : 'Start generation to edit the live run'} /><button type="submit" disabled={!liveActive || !liveCommand.trim()}>Apply</button></form></article><article className="podcast-card podcast-output-panel live-output-panel"><h3>Podcast outputs</h3><div className="output-layout"><div className="cover-art">AI<br />EVERYDAY<br />LIFE</div><div className="output-copy"><h4>{title || 'Untitled episode'} <span>{connectedJob ? String(connectedJob.status).toUpperCase() : liveStreamActive ? 'STREAMING' : 'IDLE'}</span></h4><small>{formatOptions.find((option) => option.id === format)?.label} - {speakers.length} voices - {duration}</small><p>A deep dive for {audience.toLowerCase()} in a {tone.toLowerCase()} tone with transcript, citations, chapters, and downloadable audio assets.</p><b>AI</b><b>Future</b><b>Technology</b>{currentOutput ? <em>{currentOutput.title}</em> : null}</div><div className="download-grid"><button type="button" disabled={!currentOutput} onClick={() => downloadCurrentOutput('MP3')}>MP3</button><button type="button" disabled={!currentOutput} onClick={() => downloadCurrentOutput('WAV')}>WAV</button><button type="button" onClick={() => setActionMessage('Transcript export requested.')}>Transcript</button><button type="button" onClick={() => setActionMessage('Show notes export requested.')}>Show Notes</button><button type="button" className="download-all" disabled={!currentOutput} onClick={() => downloadCurrentOutput('Download all')}>Download all</button><button type="button" onClick={() => void copyEpisodeLink()}>Copy link</button><button type="button" onClick={startGeneration}>Regenerate</button></div></div></article></section>
          <aside className="podcast-sidebar"><article className="podcast-card quality-card collapsible-card"><div className="card-heading-row"><h3>Quality gates</h3><button className="collapse-toggle" type="button" onClick={() => toggleSidebarPanel('quality')}>{collapsedPanels.quality ? 'Expand' : 'Collapse'}</button></div>{!collapsedPanels.quality ? <div className="sidebar-card-body">{mockQualityGates.map((gate) => <button type="button" key={gate.label} className={gate.status === 'Warning' ? 'warning' : undefined} onClick={() => setActionMessage(`${gate.label} gate: ${gate.status}.`)}><span>{gate.label}</span><b>{gate.status}</b></button>)}</div> : null}</article><article className="podcast-card health-card collapsible-card"><div className="card-heading-row"><h3>Session health</h3><button className="collapse-toggle" type="button" onClick={() => toggleSidebarPanel('health')}>{collapsedPanels.health ? 'Expand' : 'Collapse'}</button></div>{!collapsedPanels.health ? <div className="health-grid">{mockSessionMetrics.map((metric) => <div key={metric.label}><small>{metric.label}</small><strong>{metric.value}</strong></div>)}</div> : null}</article><article className="podcast-card recent-card collapsible-card"><div className="card-heading-row"><h3>Recent jobs</h3><span className="recent-actions"><button className="collapse-toggle" type="button" onClick={() => toggleSidebarPanel('recent')}>{collapsedPanels.recent ? 'Expand' : 'Collapse'}</button><button type="button" onClick={() => setShowAllRecentJobs((value) => !value)}>{showAllRecentJobs ? 'Show fewer' : 'View all'}</button></span></div>{!collapsedPanels.recent ? <div className="recent-job-list">{recentJobs.map((job) => <p key={`${job.id}-${job.status}`}><span className="recent-job-title" title={job.name}>{job.name}</span><OmnixStatusPill>{job.status}</OmnixStatusPill><small>{job.duration}</small><button type="button" onClick={() => selectRecentJob(job.id)}>Select</button></p>)}</div> : null}</article></aside>
        </div>
        <section className="podcast-bottom-grid"><article className="podcast-card production-assets-panel"><h3>Production assets</h3><div>{mockProductionAssetTiles.map((asset) => <section className={`asset-tile ${asset.color}`} key={asset.label}><b>{asset.label}</b><small>{asset.status}</small><button type="button" onClick={() => setActionMessage(`${asset.label}: ${asset.action} requested.`)}>{asset.action}</button></section>)}</div></article></section><p className="action-toast" role="status">{actionMessage}</p>
      </div>
    </WorkspacePanel>
  );
}
