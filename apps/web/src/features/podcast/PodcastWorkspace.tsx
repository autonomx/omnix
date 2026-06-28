// @ts-nocheck
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useRef, useState } from 'react';
import { omnixApiClient, type AssetListResponse, type JobRecord } from '../../api/client';
import type { OmnixModuleDefinition } from '../../app/modules';
import { OmnixStatusPill, WorkspacePanel } from '../../design/primitives';
import { mockPodcastSpeakerProfiles } from '../conversation-production/speakers';
import { FeatureSubmitFeedback, FeatureValidationMessage } from '../shared/FeatureSubmitFeedback';
import { buildConversationalPodcastSegments } from './scriptBuilder';
import type { PodcastFormat } from './types';
import './PodcastWorkspace.css';
import './PodcastWorkspaceLayoutFix.css';

type VoiceAsset = AssetListResponse['assets'][number];
type SpeakerDraft = ReturnType<typeof toSpeakerDraft>;
type TranscriptRow = { timestamp: string; speaker: string; text: string };
type PlayablePodcastOutput = { dataUrl: string; duration: number; jobId: string; key: string; title: string; live?: boolean };
type SpeakerVoiceAssignment = { speaker: string; voiceId: string | null; style: string; sourceSpeaker?: SpeakerDraft };

const defaultTitle = 'The Future of AI in Everyday Life';
const defaultBrief = 'Explore how artificial intelligence is shaping our daily lives, transforming work and productivity, inspiring creativity, influencing relationships, and augmenting decision-making. We will discuss opportunities, risks, and what comes next.';
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
const debugPrefix = '[PODCAST][storyteller-stitch]';
const stitchedLiveKey = 'live:stitched-preview';
const seamTrimSeconds = 0.08;
const restoreSafetySeconds = 0.02;

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
function targetWordCount(duration: string): number { return Math.max(220, Math.round(durationMinutes(duration) * wordsPerMinute)); }
function formatClock(seconds: number): string { const safe = Number.isFinite(seconds) && seconds > 0 ? Math.floor(seconds) : 0; return `${String(Math.floor(safe / 60)).padStart(2, '0')}:${String(safe % 60).padStart(2, '0')}`; }
function isTerminal(status: unknown): boolean { return terminalStatuses.includes(String(status ?? '').toLowerCase()); }
function isFailed(status: unknown): boolean { return ['failed', 'error', 'cancelled', 'canceled'].includes(String(status ?? '').toLowerCase()); }
function firstTag(value: string): string { return splitTags(value)[0] ?? 'Neutral'; }
function speakerDisplayName(speaker: string): string { return speaker.length > 18 ? `${speaker.slice(0, 17)}…` : speaker; }
function nowMs(): number { return typeof performance !== 'undefined' && performance.now ? performance.now() : Date.now(); }
function debug(message: string, detail?: unknown) { if (typeof console !== 'undefined') console.debug(debugPrefix, message, detail ?? ''); }
function voiceStoragePath(asset: VoiceAsset | undefined): string { return typeof (asset as any)?.storage_path === 'string' ? (asset as any).storage_path : ''; }
function voiceAssetId(asset: VoiceAsset | undefined): string { return typeof (asset as any)?.id === 'string' ? (asset as any).id : ''; }
function voiceAssetName(asset: VoiceAsset): string { const metadata = (asset as any).metadata ?? {}; const metadataName = typeof metadata.profile_name === 'string' ? metadata.profile_name : typeof metadata.name === 'string' ? metadata.name : ''; if (metadataName.trim()) return metadataName.trim(); const source = voiceStoragePath(asset) || voiceAssetId(asset); return source.split(/[\\/]/).pop()?.replace(/\.[^.]+$/, '') || voiceAssetId(asset) || 'Voice'; }
function voiceOptionsFromAssets(assets: VoiceAsset[]) { return assets.filter((asset) => asset.type === 'voice_profile').map((asset) => ({ id: voiceStoragePath(asset) || voiceAssetId(asset), label: voiceAssetName(asset) })).filter((voice) => voice.id); }
function jobTitle(job: { type: string; input_payload?: unknown }): string { const payload = job.input_payload as any; return payload && typeof payload.title === 'string' ? payload.title : job.type; }
function delay(ms: number) { return new Promise((resolve) => setTimeout(resolve, ms)); }
function normalizeSpeakerKey(value: string): string { return String(value || '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim(); }
function uniqueScriptSpeakerNames(segments: Array<{ speaker: string }>): string[] { return [...new Set(segments.map((segment) => String(segment.speaker || 'Speaker').trim()).filter(Boolean))]; }
function speakerCounts(segments: Array<{ speaker: string }>) { const counts: Record<string, number> = {}; for (const segment of segments) counts[segment.speaker] = (counts[segment.speaker] ?? 0) + 1; return counts; }
function podcastStages() { return [{ id: 'producer_plan', label: 'Producer Plan', resource_class: 'cpu' as const, status: 'queued' as const }, { id: 'performance_script', label: 'Performance Script', resource_class: 'cpu' as const, status: 'queued' as const }, { id: 'speaking_turns', label: 'Speaking Turns', resource_class: 'gpu:tts' as const, status: 'queued' as const }, { id: 'mix', label: 'Mix', resource_class: 'cpu' as const, status: 'queued' as const }, { id: 'podcast_renderer', label: 'Podcast Renderer', resource_class: 'cpu' as const, status: 'queued' as const }]; }
function stageState(status: unknown, index: number, activeIndex: number) { const normalized = String(status ?? '').toLowerCase(); if (isFailed(normalized)) return 'failed'; if (['completed', 'complete', 'succeeded', 'success', 'done'].includes(normalized)) return 'done'; if (['running', 'in_progress', 'active', 'processing', 'leased', 'retrying', 'queued'].includes(normalized)) return 'active'; return index === activeIndex ? 'active' : index < activeIndex ? 'done' : 'pending'; }
function safeDownloadName(value: string): string { return value.replace(/[^A-Za-z0-9_.-]+/g, '-').replace(/^-+|-+$/g, '') || 'podcast-output'; }
function readStoredTranscripts(): Record<string, TranscriptRow[]> { if (typeof window === 'undefined') return {}; try { return JSON.parse(window.localStorage.getItem(transcriptStorageKey) || '{}') || {}; } catch { return {}; } }
function writeStoredTranscripts(value: Record<string, TranscriptRow[]>): void { if (typeof window === 'undefined') return; try { window.localStorage.setItem(transcriptStorageKey, JSON.stringify(value)); } catch {} }
function transcriptRowsFromSegments(segments: Array<{ speaker: string; text: string }>, targetSeconds: number): TranscriptRow[] { if (!segments.length) return []; const step = Math.max(8, targetSeconds / segments.length); return segments.map((segment, index) => ({ timestamp: formatClock(index * step), speaker: String(segment.speaker || 'Speaker'), text: String(segment.text || '') })); }
function transcriptRowsFromJob(job: JobRecord | undefined): TranscriptRow[] { const payload = job?.input_payload as any; const scriptSegments = Array.isArray(payload?.script_segments) ? payload.script_segments : []; if (!scriptSegments.length) return []; const targetSeconds = Number(payload?.constraints?.targetDurationSeconds || payload?.target_duration_seconds || 0); return transcriptRowsFromSegments(scriptSegments.map((segment) => ({ speaker: String(segment.speaker || 'Speaker'), text: String(segment.text || '') })), targetSeconds); }

function resolveSpeakerVoiceAssignments(segments: Array<{ speaker: string }>, speakers: SpeakerDraft[], voiceOptions: Array<{ id: string; label: string }>): Record<string, SpeakerVoiceAssignment> {
  const assignments: Record<string, SpeakerVoiceAssignment> = {};
  const indexedSpeakers = speakers.map((speaker) => ({ speaker, key: normalizeSpeakerKey(speaker.name), role: normalizeSpeakerKey(speaker.role), identity: normalizeSpeakerKey(speaker.identity) }));
  uniqueScriptSpeakerNames(segments).forEach((speakerName, index) => {
    const key = normalizeSpeakerKey(speakerName);
    const matched = indexedSpeakers.find((entry) => entry.key === key || entry.role === key || entry.identity === key || (key && (entry.key.includes(key) || key.includes(entry.key))))?.speaker;
    const fallback = matched || speakers[index % Math.max(speakers.length, 1)];
    const voiceId = fallback?.voice || voiceOptions[index % Math.max(voiceOptions.length, 1)]?.id || null;
    assignments[speakerName] = { speaker: speakerName, voiceId, style: firstTag(fallback?.speakingStyle || fallback?.personality || fallback?.role || speakerName), sourceSpeaker: fallback };
  });
  return assignments;
}

function defaultVoicesFromOptions(voiceOptions: Array<{ id: string; label: string }>) { return { narrator: voiceOptions[0]?.id || null, female: voiceOptions[1]?.id || voiceOptions[0]?.id || null, male: voiceOptions[2]?.id || voiceOptions[0]?.id || null }; }

function extractPlayableOutputs(jobs: Array<JobRecord | undefined>, extraOutputs: PlayablePodcastOutput[] = []): PlayablePodcastOutput[] {
  const outputs: PlayablePodcastOutput[] = [...extraOutputs];
  const seen = new Set(outputs.map((output) => output.key));
  for (const job of jobs) {
    const refs = (job?.output_refs ?? []) as Array<{ data_url?: unknown; audio_url?: unknown; duration?: unknown; asset_id?: unknown; title?: unknown }>;
    for (const ref of refs) {
      const dataUrl = typeof ref.data_url === 'string' ? ref.data_url : typeof ref.audio_url === 'string' ? ref.audio_url : '';
      if (!dataUrl.startsWith('data:audio/') && !dataUrl.startsWith('blob:') && !dataUrl.startsWith('/api/')) continue;
      const title = typeof ref.title === 'string' && ref.title.trim() ? ref.title : jobTitle(job as JobRecord);
      const key = `${job?.id ?? 'job'}:${String(ref.asset_id || title || outputs.length)}`;
      if (seen.has(key)) continue;
      seen.add(key);
      outputs.push({ dataUrl, duration: Number(ref.duration || 0), jobId: job?.id || 'job', key, title });
    }
  }
  return outputs;
}

async function waitForPlayableJob(job: JobRecord, timeoutMs = 120_000): Promise<JobRecord> {
  if (extractPlayableOutputs([job]).length || isTerminal(job.status)) return job;
  const startedAt = Date.now();
  let latest = job;
  while (Date.now() - startedAt < timeoutMs) {
    await delay(1_250);
    try {
      latest = await omnixApiClient.getJob(job.id);
      debug('polled job', { id: latest.id, status: latest.status, outputs: extractPlayableOutputs([latest]).length });
      if (extractPlayableOutputs([latest]).length || isTerminal(latest.status)) return latest;
    } catch (error) {
      console.warn(debugPrefix, 'poll failed', error);
    }
  }
  return latest;
}

async function arrayBufferFromAudioUrl(url: string): Promise<ArrayBuffer> {
  if (url.startsWith('data:')) {
    const [, payload = ''] = url.split(',', 2);
    const isBase64 = /^data:[^,]+;base64,/i.test(url);
    const binary = isBase64 ? atob(payload) : decodeURIComponent(payload);
    const bytes = new Uint8Array(binary.length);
    for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index) & 0xff;
    return bytes.buffer;
  }
  const response = await fetch(url);
  return response.arrayBuffer();
}

function encodeWavFromFloat32(samples: Float32Array, sampleRate: number): Blob {
  const dataSize = samples.length * 2;
  const buffer = new ArrayBuffer(44 + dataSize);
  const view = new DataView(buffer);
  const writeString = (offset: number, value: string) => { for (let index = 0; index < value.length; index += 1) view.setUint8(offset + index, value.charCodeAt(index)); };
  writeString(0, 'RIFF'); view.setUint32(4, 36 + dataSize, true); writeString(8, 'WAVE'); writeString(12, 'fmt '); view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true); view.setUint32(24, sampleRate, true); view.setUint32(28, sampleRate * 2, true); view.setUint16(32, 2, true); view.setUint16(34, 16, true); writeString(36, 'data'); view.setUint32(40, dataSize, true);
  let offset = 44;
  for (let index = 0; index < samples.length; index += 1, offset += 2) {
    const sample = Math.max(-1, Math.min(1, samples[index]));
    view.setInt16(offset, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true);
  }
  return new Blob([buffer], { type: 'audio/wav' });
}

function copyResampledMono(source: AudioBuffer, destination: Float32Array, offset: number, targetSampleRate: number, trimStartSamples = 0, fadeInSamples = 0) {
  const sourceData = source.getChannelData(0);
  const targetLength = Math.max(1, Math.round(source.duration * targetSampleRate));
  const copiedLength = Math.max(1, targetLength - trimStartSamples);
  const ratio = source.sampleRate / targetSampleRate;
  for (let index = 0; index < copiedLength; index += 1) {
    const sourceIndex = source.sampleRate === targetSampleRate ? index + trimStartSamples : (index + trimStartSamples) * ratio;
    const before = Math.floor(sourceIndex);
    const after = Math.min(before + 1, sourceData.length - 1);
    const fraction = sourceIndex - before;
    const gain = fadeInSamples > 0 && index < fadeInSamples ? index / fadeInSamples : 1;
    destination[offset + index] = (sourceData[before] * (1 - fraction) + sourceData[after] * fraction) * gain;
  }
  return copiedLength;
}

async function stitchLiveOutputs(outputs: PlayablePodcastOutput[]): Promise<PlayablePodcastOutput | null> {
  if (!outputs.length) return null;
  const fallback = outputs[outputs.length - 1];
  const title = `Live preview stitched ${outputs.length} / ${outputs.length}`;
  if (outputs.length === 1 || typeof window === 'undefined') return { ...fallback, key: stitchedLiveKey, title, live: true };
  const AudioContextCtor = (window as any).AudioContext || (window as any).webkitAudioContext;
  if (!AudioContextCtor || !URL?.createObjectURL) {
    return { ...fallback, key: stitchedLiveKey, title, duration: outputs.reduce((sum, output) => sum + Number(output.duration || 0), 0) || fallback.duration, live: true };
  }
  const context = new AudioContextCtor();
  try {
    const buffers = await Promise.all(outputs.map(async (output) => context.decodeAudioData(await arrayBufferFromAudioUrl(output.dataUrl))));
    const sampleRate = buffers[0]?.sampleRate || 24000;
    const trimSamples = buffers.map((buffer, index) => index === 0 ? 0 : Math.min(Math.round(seamTrimSeconds * sampleRate), Math.max(0, Math.round(buffer.duration * sampleRate) - 1)));
    const fadeSamples = Math.max(1, Math.round(0.006 * sampleRate));
    const totalLength = buffers.reduce((sum, buffer, index) => sum + Math.max(1, Math.round(buffer.duration * sampleRate) - trimSamples[index]), 0);
    const stitched = new Float32Array(totalLength);
    let offset = 0;
    buffers.forEach((buffer, index) => { offset += copyResampledMono(buffer, stitched, offset, sampleRate, trimSamples[index], index === 0 ? 0 : fadeSamples); });
    const blob = encodeWavFromFloat32(stitched, sampleRate);
    return { dataUrl: URL.createObjectURL(blob), duration: stitched.length / sampleRate, jobId: 'live-preview', key: stitchedLiveKey, title, live: true };
  } finally {
    try { await context.close(); } catch {}
  }
}

function textFromChatResponse(response: any): string {
  const direct = [response?.content, response?.text, response?.response, response?.reply, response?.message?.content, response?.assistant?.content, response?.assistant_message?.content, response?.output].find((value) => typeof value === 'string' && value.trim());
  if (direct) return String(direct);
  const messages = Array.isArray(response?.messages) ? response.messages : Array.isArray(response?.session?.messages) ? response.session.messages : [];
  const assistant = [...messages].reverse().find((message) => String(message?.role || '').toLowerCase() === 'assistant' && typeof message?.content === 'string');
  return assistant?.content || '';
}

function parseSegmentsFromLlm(raw: string): Array<{ index: number; speaker: string; text: string }> {
  const stripped = raw.replace(/```(?:json)?/gi, '').replace(/```/g, '').trim();
  const jsonMatch = stripped.match(/\{[\s\S]*\}/) || stripped.match(/\[[\s\S]*\]/);
  if (jsonMatch) {
    try {
      const parsed = JSON.parse(jsonMatch[0]);
      const rawSegments = Array.isArray(parsed) ? parsed : Array.isArray(parsed?.segments) ? parsed.segments : Array.isArray(parsed?.script_segments) ? parsed.script_segments : [];
      const segments = rawSegments.map((segment: any, index: number) => ({ index, speaker: String(segment?.speaker || segment?.name || 'Speaker').trim(), text: String(segment?.text || segment?.line || segment?.content || '').trim() })).filter((segment) => segment.speaker && segment.text);
      if (segments.length) return segments;
    } catch (error) { console.warn(debugPrefix, 'LLM JSON parse failed', error); }
  }
  return stripped.split('\n').map((line, index) => {
    const match = line.match(/^\s*([^:]{2,40})\s*:\s*(.+)$/);
    return match ? { index, speaker: match[1].trim(), text: match[2].trim() } : null;
  }).filter(Boolean) as Array<{ index: number; speaker: string; text: string }>;
}

async function generateLlmPodcastSegments(args: { title: string; brief: string; audience: string; duration: string; format: PodcastFormat; speakers: SpeakerDraft[]; tone: string; language: string }) {
  const targetLines = Math.min(48, Math.max(args.speakers.length * 4, Math.ceil(targetWordCount(args.duration) / 70)));
  const validNames = args.speakers.map((speaker) => speaker.name).join(', ');
  const speakerList = args.speakers.map((speaker) => `${speaker.name} (${speaker.role}): identity=${speaker.identity}; beliefs=${speaker.beliefs}; personality=${speaker.personality}; speaking_style=${speaker.speakingStyle}; goal=${speaker.goal}; instructions=${speaker.instructions || 'none'}`).join('\n');
  const prompt = `Generate a real, speaker-tagged podcast script. Return JSON only with this shape: {"segments":[{"speaker":"${args.speakers[0]?.name || 'Host'}","text":"spoken line"}]}.
Topic: ${args.title}
Brief: ${args.brief}
Audience: ${args.audience}
Format: ${args.format}
Tone: ${args.tone}
Language: ${args.language}
Target lines: ${targetLines}
Valid speaker names: ${validNames}
Speakers, use these exact names only:
${speakerList}
Make the dialogue specific to the topic. Avoid stage directions, markdown, bullets, narrator notes, and any speaker names outside the valid list.`;
  try {
    const session = await omnixApiClient.createChatSession({ title: `Podcast script: ${args.title}`.slice(0, 64), system_prompt: 'You are a podcast scriptwriter. Return only valid JSON requested by the user.' });
    const response = await omnixApiClient.sendChatMessage(session.id, { content: prompt });
    const rows = parseSegmentsFromLlm(textFromChatResponse(response));
    if (rows.length >= Math.min(2, args.speakers.length)) return rows.map((segment, index) => ({ ...segment, index }));
  } catch (error) {
    console.warn(debugPrefix, 'LLM script generation unavailable; falling back to local planner.', error);
  }
  return buildConversationalPodcastSegments(args.title, args.brief, args.audience, args.speakers, args.duration).map((segment, index) => ({ index, speaker: segment.speaker, text: segment.text }));
}

function buildSingleSpeakerJobPayload(args: { title: string; language: string; segment: { index: number; speaker: string; text: string }; voiceOptions: Array<{ id: string; label: string }>; voiceAssignments: Record<string, SpeakerVoiceAssignment> }) {
  const assignment = args.voiceAssignments[args.segment.speaker];
  const voiceId = assignment?.voiceId || args.voiceOptions[0]?.id || null;
  return { title: `${args.title} - ${args.segment.speaker} ${args.segment.index + 1}`, text: args.segment.text, provider_id: null, speaker: args.segment.speaker, voice_id: voiceId, language: args.language, script_mode: 'single_speaker', script_speakers: [{ name: args.segment.speaker, count: 1 }], script_segments: [args.segment], character_voice_assignments: [{ speaker: args.segment.speaker, voice_id: voiceId, style: assignment?.style || 'Neutral', line_count: 1 }], voice_mapping: { [args.segment.speaker]: voiceId }, default_voices: defaultVoicesFromOptions(args.voiceOptions), output_settings: outputSettings, audio_effects: audioEffects, save_output: true, renderer: 'podcast-live-preview' };
}

function buildPodcastJobPayload(args: any) {
  const counts = speakerCounts(args.segments);
  const targetSeconds = durationSeconds(args.duration);
  const assignments = args.voiceAssignments || resolveSpeakerVoiceAssignments(args.segments, args.speakers, args.voiceOptions);
  const scriptSpeakerNames = Object.keys(counts);
  const voiceMapping = Object.fromEntries(scriptSpeakerNames.map((name) => [name, assignments[name]?.voiceId || null]));
  return { title: args.title, brief: args.brief, format: args.format, audience: args.audience, duration_minutes: durationMinutes(args.duration), target_duration_seconds: targetSeconds, target_word_count: targetWordCount(args.duration), tone: args.tone, language: args.language, generation_style: args.generationStyle, review_policy: { mode: args.generationStyle }, renderer: 'podcast', text: args.segments.map((segment) => `${segment.speaker}: ${segment.text}`).join('\n'), provider_id: null, speaker: scriptSpeakerNames[0] || args.speakers[0]?.name || 'Host', voice_id: assignments[scriptSpeakerNames[0]]?.voiceId || args.voiceOptions[0]?.id || null, script_mode: args.segments.length > 1 ? 'multi_speaker' : 'single_speaker', script_speakers: scriptSpeakerNames.map((name) => ({ name, count: counts[name] })), script_segments: args.segments, character_voice_assignments: scriptSpeakerNames.map((name) => ({ speaker: name, voice_id: assignments[name]?.voiceId || null, style: assignments[name]?.style || 'Neutral', line_count: counts[name] ?? 0 })), voice_mapping: voiceMapping, default_voices: defaultVoicesFromOptions(args.voiceOptions), output_settings: outputSettings, audio_effects: audioEffects, save_output: true, speakers: args.speakers.map((speaker) => ({ id: speaker.id, name: speaker.name, role: speaker.role, identity: speaker.identity, beliefs: splitTags(speaker.beliefs), personality: splitTags(speaker.personality), speakingStyle: splitTags(speaker.speakingStyle), defaultGoal: speaker.goal, speakerInstructions: speaker.instructions, voiceMapping: { speakerId: speaker.id, voiceId: speaker.voice, voiceDisplayName: args.voiceOptions.find((voice) => voice.id === speaker.voice)?.label || speaker.voice, previewAvailable: Boolean(speaker.voice) } })), constraints: { maxDurationSeconds: targetSeconds, targetDurationSeconds: targetSeconds, targetWordCount: targetWordCount(args.duration), maxSpeakerTurnSeconds: Number.parseInt(args.maxTurnSeconds, 10) || 45, citationRequired: true, familyFriendly: true, readingLevel: 'Grade 8', avoidTopics: ['Politics'], requiredTopics: ['practical examples', 'risks', 'future outlook'], disallowedClaims: [], tone: args.tone, audience: args.audience, language: args.language } };
}

export function PodcastWorkspace({ module }: { module: OmnixModuleDefinition }) {
  const queryClient = useQueryClient();
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const selectedOutputKeyRef = useRef('');
  const currentOutputRef = useRef<PlayablePodcastOutput | null>(null);
  const pendingOutputRef = useRef<PlayablePodcastOutput | null>(null);
  const livePiecesRef = useRef<PlayablePodcastOutput[]>([]);
  const stitchedUrlRef = useRef('');
  const restoreRef = useRef<{ time: number; play: boolean; capturedAt: number } | null>(null);
  const autoplayStartedRef = useRef(false);
  const userPausedRef = useRef(false);
  const generationVersionRef = useRef(0);

  const jobsQuery = useQuery({ queryKey: ['platform', 'jobs'], queryFn: async () => { try { return await omnixApiClient.listJobs(); } catch { return { jobs: [] }; } }, retry: false, refetchInterval: false, refetchOnWindowFocus: false });
  const assetsQuery = useQuery({ queryKey: ['platform', 'assets'], queryFn: async () => { try { return await omnixApiClient.listAssets(); } catch { return { assets: [] }; } }, retry: false, refetchInterval: false, refetchOnWindowFocus: false });

  const [title, setTitle] = useState(defaultTitle);
  const [brief, setBrief] = useState(defaultBrief);
  const [audience, setAudience] = useState('Software Engineers');
  const [duration, setDuration] = useState('20 min');
  const [tone, setTone] = useState('Professional');
  const [language, setLanguage] = useState('English (US)');
  const [format, setFormat] = useState<PodcastFormat>('debate');
  const [generationStyle, setGenerationStyle] = useState('automatic');
  const [speakers, setSpeakers] = useState(() => mockPodcastSpeakerProfiles.map(toSpeakerDraft));
  const [transcript, setTranscript] = useState<TranscriptRow[]>([]);
  const [storedTranscripts, setStoredTranscripts] = useState<Record<string, TranscriptRow[]>>(() => readStoredTranscripts());
  const [directorNote, setDirectorNote] = useState('No live production is running. Configure the episode, then press Generate live podcast.');
  const [liveCommand, setLiveCommand] = useState('');
  const [playbackRate, setPlaybackRate] = useState('1.0x');
  const [selectedOutputKey, setSelectedOutputKey] = useState('');
  const [livePieces, setLivePieces] = useState<PlayablePodcastOutput[]>([]);
  const [currentOutput, setCurrentOutput] = useState<PlayablePodcastOutput | null>(null);
  const [liveAutoplay, setLiveAutoplay] = useState(false);
  const [actionMessage, setActionMessage] = useState('Ready for automatic production.');

  const voiceOptions = useMemo(() => voiceOptionsFromAssets(assetsQuery.data?.assets ?? []), [assetsQuery.data?.assets]);
  const podcastJobs = jobsQuery.data?.jobs.filter((job) => job.module === 'podcast') ?? [];
  const activeJob = podcastJobs.find((job) => !isTerminal(job.status));
  const connectedJob = selectedOutputKey === '__new__' ? undefined : createJobMutationData() ?? activeJob ?? podcastJobs[0];
  const persistedTranscript = connectedJob?.id ? storedTranscripts[connectedJob.id] ?? [] : [];
  const transcriptRows = selectedOutputKey === '__new__' ? [] : transcript.length ? transcript : persistedTranscript.length ? persistedTranscript : transcriptRowsFromJob(connectedJob);
  const liveActive = selectedOutputKey === '__script__' || selectedOutputKey === '__streaming__' || Boolean(activeJob && !isTerminal(activeJob.status));

  function createJobMutationData() { return createJobMutation.data as JobRecord | undefined; }
  function selectOutputKey(key: string) { selectedOutputKeyRef.current = key; setSelectedOutputKey(key); }
  function revokeStitchedUrl() { const url = stitchedUrlRef.current; if (url && url.startsWith('blob:') && typeof URL !== 'undefined') URL.revokeObjectURL(url); stitchedUrlRef.current = ''; }
  function clearAudioElement() { const audio = audioRef.current; if (!audio) return; try { audio.pause(); audio.removeAttribute('src'); audio.load(); } catch {} restoreRef.current = null; }
  function clearPreviewState() { pendingOutputRef.current = null; livePiecesRef.current = []; generationVersionRef.current += 1; revokeStitchedUrl(); setLivePieces([]); setCurrentOutput(null); currentOutputRef.current = null; autoplayStartedRef.current = false; userPausedRef.current = false; }

  function installOutput(output: PlayablePodcastOutput, options: { restoreTime?: number; shouldPlay?: boolean } = {}) {
    const oldUrl = stitchedUrlRef.current;
    if (output.dataUrl.startsWith('blob:')) stitchedUrlRef.current = output.dataUrl;
    restoreRef.current = { time: options.restoreTime ?? audioRef.current?.currentTime ?? 0, play: Boolean(options.shouldPlay), capturedAt: nowMs() };
    currentOutputRef.current = output;
    setCurrentOutput(output);
    selectOutputKey(output.key);
    if (oldUrl && oldUrl.startsWith('blob:') && oldUrl !== output.dataUrl && typeof URL !== 'undefined') window.setTimeout(() => URL.revokeObjectURL(oldUrl), 30_000);
  }

  function maybeInstallStitchedOutput(output: PlayablePodcastOutput) {
    const audio = audioRef.current;
    const current = currentOutputRef.current;
    if (current?.live && audio && !audio.paused && !audio.ended) {
      pendingOutputRef.current = output;
      debug('deferred stitched refresh until current chunk ends', { currentTime: audio.currentTime, duration: audio.duration, pieces: livePiecesRef.current.length });
      return;
    }
    pendingOutputRef.current = null;
    installOutput(output, { restoreTime: audio?.currentTime || 0, shouldPlay: false });
  }

  async function rebuildStitchedPreview(outputs: PlayablePodcastOutput[]) {
    const version = ++generationVersionRef.current;
    const stitched = await stitchLiveOutputs(outputs);
    if (!stitched || version !== generationVersionRef.current) return;
    maybeInstallStitchedOutput(stitched);
  }

  function queueLiveOutput(output: PlayablePodcastOutput) {
    setLivePieces((current) => {
      const next = [...current, output];
      livePiecesRef.current = next;
      void rebuildStitchedPreview(next);
      return next;
    });
    if (!selectedOutputKeyRef.current || selectedOutputKeyRef.current.startsWith('__')) selectOutputKey(stitchedLiveKey);
  }

  useEffect(() => { currentOutputRef.current = currentOutput; }, [currentOutput]);
  useEffect(() => { if (!voiceOptions.length) return; setSpeakers((current) => current.map((speaker, index) => speaker.voice && voiceOptions.some((voice) => voice.id === speaker.voice) ? speaker : { ...speaker, voice: voiceOptions[index % voiceOptions.length].id })); }, [voiceOptions.map((voice) => voice.id).join('|')]);
  useEffect(() => () => { clearPreviewState(); }, []);
  useEffect(() => {
    const audio = audioRef.current;
    if (!audio || !currentOutput) return;
    audio.playbackRate = Number.parseFloat(playbackRate) || 1;
    if (!liveAutoplay || !currentOutput.live || autoplayStartedRef.current) return;
    autoplayStartedRef.current = true;
    const timer = window.setTimeout(() => {
      const playResult = audio.play();
      if (playResult?.catch) playResult.catch(() => setActionMessage('Audio is ready. Press play if the browser blocked autoplay.'));
    }, 50);
    return () => window.clearTimeout(timer);
  }, [currentOutput?.key, currentOutput?.dataUrl, liveAutoplay, playbackRate]);

  const createJobMutation = useMutation({
    mutationFn: async () => {
      const segments = await generateLlmPodcastSegments({ title, brief, audience, duration, format, speakers, tone, language });
      const rows = transcriptRowsFromSegments(segments, durationSeconds(duration));
      const voiceAssignments = resolveSpeakerVoiceAssignments(segments, speakers, voiceOptions);
      setTranscript(rows);
      setLiveAutoplay(true);
      selectOutputKey('__streaming__');
      setDirectorNote('Script is ready. Live preview chunks are stitched into one growing stream. The first chunk can auto-start; later chunks respect pause and attach at chunk boundaries.');
      setActionMessage(`Script ready: ${segments.length} speaking turns. Starting stitched live audio preview...`);

      for (const segment of segments) {
        const segmentJob = await omnixApiClient.createJob({ module: 'podcast', type: 'tts.synthesize', resource_class: 'gpu:tts', priority: 1, input_payload: buildSingleSpeakerJobPayload({ title, language, segment, voiceOptions, voiceAssignments }), stages: [{ id: 'prepare_turn', label: 'Prepare speaking turn', resource_class: 'cpu', status: 'queued' }, { id: 'voice_turn', label: `Voice Turn: ${segment.speaker}`, resource_class: 'gpu:tts', status: 'queued' }] }, { timeoutMs: 120000, timeoutMessage: 'Podcast live preview turn is still running.' });
        const completedSegmentJob = await waitForPlayableJob(segmentJob, 120000);
        const output = extractPlayableOutputs([completedSegmentJob])[0];
        if (output) {
          const liveOutput = { ...output, key: `live:${segment.index}:${output.key}`, title: `${segment.speaker}: voice mapped`, live: true };
          queueLiveOutput(liveOutput);
          setActionMessage(`Stitched live preview ${segment.index + 1}/${segments.length}: ${segment.speaker}`);
        } else if (isFailed(completedSegmentJob.status)) {
          setActionMessage(`Live preview turn failed: ${segment.speaker}`);
        }
      }

      setDirectorNote('Live preview is stitched. Rendering the single final podcast output for seeking, replay, and download.');
      setActionMessage('Live preview stitched. Rendering final podcast audio...');
      const finalJob = await omnixApiClient.createJob({ module: 'podcast', type: 'tts.multi_speaker_synthesize', resource_class: 'gpu:tts', priority: 0, input_payload: buildPodcastJobPayload({ title, brief, format, audience, duration, tone, language, generationStyle, speakers, voiceOptions, voiceAssignments, segments, maxTurnSeconds: '45' }), stages: podcastStages() }, { timeoutMs: 180000, timeoutMessage: 'Final podcast render is still running.' });
      const completedFinalJob = await waitForPlayableJob(finalJob, 180000);
      if (rows.length) setStoredTranscripts((current) => { const next = { ...current, [completedFinalJob.id]: rows }; writeStoredTranscripts(next); return next; });
      return completedFinalJob;
    },
    onMutate: () => { clearAudioElement(); clearPreviewState(); setTranscript([]); setLiveAutoplay(false); selectOutputKey('__script__'); setDirectorNote('Generating a real speaker-tagged script with the configured chat provider.'); setActionMessage('Requesting podcast script from LLM...'); },
    onSuccess: async (job) => { const output = extractPlayableOutputs([job])[0]; if (isFailed(job.status)) { setDirectorNote('Podcast generation failed.'); setActionMessage('Podcast generation failed.'); } else { setDirectorNote(output ? 'Final podcast audio is ready. The stitched live preview stays active until you select the final render.' : 'Podcast render completed but no playable audio output was attached.'); setActionMessage(output ? `Podcast audio ready: ${job.id}` : `Podcast production completed without playable audio: ${job.id}`); } await Promise.all([queryClient.invalidateQueries({ queryKey: ['platform', 'jobs'] }), queryClient.invalidateQueries({ queryKey: ['platform', 'assets'] })]); },
    onError: (error) => { setDirectorNote(error instanceof Error ? error.message : 'Podcast request failed.'); setActionMessage(error instanceof Error ? error.message : 'Podcast request failed.'); setLiveAutoplay(false); },
  });

  function startGeneration() { if (!brief.trim()) return; createJobMutation.mutate(); }
  function updateSpeaker(id: string, field: string, value: string) { setSpeakers((current) => current.map((speaker) => speaker.id === id ? { ...speaker, [field]: value } : speaker)); }
  function addParticipant() { const next = speakers.length + 1; setSpeakers((current) => [...current, { id: `guest_${next}`, name: `Guest ${next}`, role: 'Guest Analyst', avatar: `G${next}`, identity: 'Guest Analyst', beliefs: '', personality: '', speakingStyle: '', goal: '', instructions: '', voice: voiceOptions[0]?.id ?? '' }]); setActionMessage('Added participant.'); }
  function resetPodcast() { clearAudioElement(); clearPreviewState(); setTitle(''); setBrief(''); setDuration('5 min'); setTranscript([]); setLiveAutoplay(false); setDirectorNote('New podcast request cleared. Add a title and brief, then generate.'); selectOutputKey('__new__'); setActionMessage('New podcast ready.'); }
  function submitLiveCommand() { const command = liveCommand.trim(); if (!command) return; setDirectorNote(`Director note: ${command}`); setTranscript((lines) => [...lines, { timestamp: formatClock(lines.length * 15), speaker: 'Director', text: command }]); setLiveCommand(''); }
  function selectRecentJob(jobId: string) { const job = podcastJobs.find((entry) => entry.id === jobId); const output = extractPlayableOutputs([job])[0]; const rows = storedTranscripts[jobId] ?? transcriptRowsFromJob(job); if (rows.length) setTranscript(rows); if (output) installOutput(output, { shouldPlay: false }); setActionMessage(output ? `Selected audio output: ${output.title}.` : `Selected job ${jobId}; no playable audio output is attached yet.`); }
  function downloadCurrentOutput(label = 'Podcast audio') { if (!currentOutput || typeof document === 'undefined') { setActionMessage('Generate podcast audio before downloading.'); return; } const link = document.createElement('a'); link.href = currentOutput.dataUrl; link.download = `${safeDownloadName(currentOutput.title || title)}.wav`; link.click(); setActionMessage(`${label}: download started.`); }
  async function copyEpisodeLink() { const link = typeof window !== 'undefined' ? `${window.location.href.split('#')[0]}#${connectedJob?.id ?? 'podcast'}` : connectedJob?.id ?? 'podcast'; try { await navigator.clipboard?.writeText(link); setActionMessage('Podcast link copied.'); } catch { setActionMessage(`Podcast link: ${link}`); } }
  function maybeInstallPendingWhilePaused() { const audio = audioRef.current; if (!pendingOutputRef.current || (audio && !audio.paused && !audio.ended)) return; const pending = pendingOutputRef.current; pendingOutputRef.current = null; installOutput(pending, { restoreTime: audio?.currentTime || 0, shouldPlay: false }); }
  function onAudioLoadedMetadata(event: any) { const audio = event.currentTarget; audio.playbackRate = Number.parseFloat(playbackRate) || 1; const restore = restoreRef.current; if (!restore) return; restoreRef.current = null; const drift = restore.play ? Math.max(0, (nowMs() - restore.capturedAt) / 1000) + restoreSafetySeconds : 0; if (restore.time > 0 && Number.isFinite(audio.duration)) audio.currentTime = Math.min(restore.time + drift, Math.max(0, audio.duration - 0.05)); if (restore.play) { const playResult = audio.play(); if (playResult?.catch) playResult.catch(() => setActionMessage('Audio is ready. Press play if the browser blocked autoplay.')); } }
  function onAudioEnded() { const audio = audioRef.current; if (pendingOutputRef.current) { const pending = pendingOutputRef.current; pendingOutputRef.current = null; installOutput(pending, { restoreTime: currentOutputRef.current?.duration || audio?.currentTime || 0, shouldPlay: !userPausedRef.current }); return; } const finalOutput = extractPlayableOutputs([createJobMutation.data, ...podcastJobs]).find((output) => !output.live); if (finalOutput) installOutput(finalOutput, { shouldPlay: false }); }

  const liveStatus = createJobMutation.isPending ? (selectedOutputKey === '__script__' ? 'SCRIPTING' : 'STREAMING') : connectedJob ? String(connectedJob.status).toUpperCase() : 'IDLE';
  const stages = createJobMutation.isPending ? podcastStages().map((stage, index) => ({ ...stage, state: index < 2 ? 'done' : index === 2 ? 'active' : 'pending' })) : (connectedJob?.stages?.length ? connectedJob.stages.map((stage, index) => ({ id: stage.id, label: stage.label, state: stageState(stage.status, index, 0) })) : podcastStages().map((stage) => ({ ...stage, state: 'pending' })));
  const recentJobs = podcastJobs.length ? podcastJobs.slice(0, 6).map((job) => ({ id: job.id, name: jobTitle(job), status: job.status, duration })) : [];
  const showBriefError = brief.trim().length === 0 && createJobMutation.isIdle === false;

  return (
    <WorkspacePanel className="podcast-workspace-panel">
      <div className="podcast-studio-shell">
        <header className="podcast-studio-header"><div><p className="eyebrow">Conversation engine</p><h2 id="module-title">{module.label}</h2><p>Create a real LLM-generated podcast script, stitch live preview turns into one growing stream, then keep one final render for playback and download.</p></div><code>/podcast-renderer</code></header>
        <div className="podcast-studio-grid">
          <section className="podcast-studio-stack">
            <article className="podcast-card episode-setup-card">
              <div className="card-heading-row"><h3>1. Episode setup</h3><button className="ghost-button compact" type="button" onClick={resetPodcast}>New podcast</button></div>
              <div className="episode-setup-grid"><div className="podcast-field-stack"><label>Topic / Episode title<input value={title} onChange={(event) => setTitle(event.target.value)} /></label><label>Episode brief<textarea rows={5} value={brief} onChange={(event) => setBrief(event.target.value)} /><small>{brief.length}/2000</small></label><label>Audience<select value={audience} onChange={(event) => setAudience(event.target.value)}><option>Software Engineers</option><option>General Public</option><option>Executives</option><option>Students</option><option>Experts</option></select></label></div><div className="podcast-config-stack"><span className="podcast-label">Podcast format</span><div className="format-card-grid">{formatOptions.map((option) => <button key={option.id} type="button" className={option.id === format ? 'selected' : undefined} onClick={() => setFormat(option.id)}><strong>{option.label}</strong><small>{option.description}</small></button>)}</div><div className="podcast-select-grid"><label>Duration<select value={duration} onChange={(event) => setDuration(event.target.value)}>{durationOptions.map((option) => <option key={option}>{option}</option>)}</select></label><label>Tone<select value={tone} onChange={(event) => setTone(event.target.value)}><option>Professional</option><option>Conversational</option><option>Humorous</option></select></label><label>Language<select value={language} onChange={(event) => setLanguage(event.target.value)}><option>English (US)</option><option>English (UK)</option></select></label></div><label>Generation Style<select value={generationStyle} onChange={(event) => setGenerationStyle(event.target.value)}><option value="automatic">Automatic</option><option value="guided">Guided</option></select></label></div></div>
            </article>
            <article className="podcast-card">
              <div className="card-heading-row"><h3>2. Participants and voice casting</h3><small>{voiceOptions.length ? `Loaded ${voiceOptions.length} Voice Library voice${voiceOptions.length === 1 ? '' : 's'}` : 'No Voice Library voices found'}</small></div>
              <div className="speaker-table editable-speaker-table"><div className="speaker-row speaker-header"><span>Speaker</span><span>Identity</span><span>Voice</span><span>Beliefs</span><span>Personality</span><span>Speaking style</span><span>Goal this episode</span><span>Instructions</span></div>{speakers.map((speaker) => <div className="speaker-row editable-speaker-row" key={speaker.id}><span className="speaker-cell-main"><b className={`speaker-avatar ${speaker.id}`}>{speaker.avatar}</b><span><input value={speaker.name} onChange={(event) => updateSpeaker(speaker.id, 'name', event.target.value)} /><input value={speaker.role} onChange={(event) => updateSpeaker(speaker.id, 'role', event.target.value)} /></span></span><span><input value={speaker.identity} onChange={(event) => updateSpeaker(speaker.id, 'identity', event.target.value)} /></span><span><select aria-label={`${speaker.name} voice`} value={speaker.voice} onChange={(event) => updateSpeaker(speaker.id, 'voice', event.target.value)}>{voiceOptions.map((voice) => <option key={voice.id} value={voice.id}>{voice.label}</option>)}{!voiceOptions.length ? <option value="">No cloned voices</option> : null}</select></span><span><textarea rows={2} value={speaker.beliefs} onChange={(event) => updateSpeaker(speaker.id, 'beliefs', event.target.value)} /></span><span><textarea rows={2} value={speaker.personality} onChange={(event) => updateSpeaker(speaker.id, 'personality', event.target.value)} /></span><span><textarea rows={2} value={speaker.speakingStyle} onChange={(event) => updateSpeaker(speaker.id, 'speakingStyle', event.target.value)} /></span><span><textarea rows={2} value={speaker.goal} onChange={(event) => updateSpeaker(speaker.id, 'goal', event.target.value)} /></span><span><textarea rows={2} value={speaker.instructions} onChange={(event) => updateSpeaker(speaker.id, 'instructions', event.target.value)} /></span></div>)}</div><button className="ghost-button" type="button" onClick={addParticipant}>+ Add participant</button>
            </article>
            <form onSubmit={(event) => { event.preventDefault(); startGeneration(); }}><button className="podcast-generate-button" type="submit" disabled={createJobMutation.isPending}>Generate live podcast</button></form>
            <FeatureValidationMessage show={showBriefError} message="Enter an episode brief before generating a podcast." />
            <FeatureSubmitFeedback error={createJobMutation.error} errorPrefix="Podcast request" isError={createJobMutation.isError} isPending={createJobMutation.isPending} jobId={createJobMutation.data?.id} pendingMessage="Generating script and stitching preview audio..." successPrefix="Podcast production queued" />
          </section>
          <section className="podcast-live-column">
            <article className={`podcast-card live-production-card ${liveActive ? 'streaming' : 'idle'}`}>
              <div className="card-heading-row"><h3>Live production</h3><span className="auto-badge">{liveStatus}</span></div>
              <div className="stage-rail">{stages.map((stage, index) => <span key={`${stage.id}-${stage.label}`} className={stage.state}>{stage.state === 'done' ? 'OK' : stage.state === 'failed' ? '!' : index + 1}<small>{stage.label}</small></span>)}</div>
              <div className="director-note"><b>Director</b><span>{directorNote}</span></div>
              <div className={`waveform ${liveActive ? 'streaming' : 'idle'}`} aria-hidden="true">{Array.from({ length: 64 }, (_, index) => <i key={index} style={{ height: `${18 + ((index * 17 + transcriptRows.length * 5) % 42)}px` }} />)}</div>
              <section className="live-transcript-section"><div className="card-heading-row"><h4>Transcript</h4><small>{transcriptRows.length ? `${transcriptRows.length} line${transcriptRows.length === 1 ? '' : 's'}` : 'Waiting for script'}</small></div><div className="live-transcript">{transcriptRows.length ? transcriptRows.map((line, index) => <p key={`${line.timestamp}-${line.speaker}-${index}`}><time>{line.timestamp}</time><b title={line.speaker}>{speakerDisplayName(line.speaker)}</b><span>{line.text}</span></p>) : <div className="live-empty-state"><strong>No live transcript yet</strong><span>Press Generate live podcast to request an LLM script and start live preview audio.</span></div>}</div></section>
              <div className="podcast-audio-player" aria-label="Podcast audio player"><div className="audio-player-heading"><span>{currentOutput ? currentOutput.title : selectedOutputKey === '__script__' ? 'Generating podcast script...' : selectedOutputKey === '__streaming__' || selectedOutputKey === stitchedLiveKey ? 'Waiting for first stitched live audio segment...' : 'No podcast audio yet'}</span><small>{currentOutput?.live ? `LIVE STITCHED ${livePieces.length} / ${transcriptRows.length || livePieces.length}` : currentOutput ? 'AUDIO READY' : createJobMutation.isPending ? liveStatus : 'Generate a completed podcast to enable playback'}</small></div>{createJobMutation.isPending && !currentOutput ? <p className="streaming-note">The first preview chunk can auto-start. New chunks are stitched in at safe boundaries and will not restart playback after you pause.</p> : null}<audio key={currentOutput?.key || selectedOutputKey || 'podcast-empty-audio'} ref={audioRef} src={currentOutput?.dataUrl ?? ''} controls preload="auto" onLoadedMetadata={onAudioLoadedMetadata} onCanPlay={() => currentOutput && setActionMessage(`${currentOutput.live ? 'Stitched live preview' : 'Audio available'}: ${currentOutput.title}`)} onPause={() => { userPausedRef.current = true; maybeInstallPendingWhilePaused(); }} onPlay={() => { userPausedRef.current = false; }} onError={() => currentOutput && setActionMessage('The generated audio could not be loaded by the browser.')} onEnded={onAudioEnded} /><div className="audio-toolbar"><label>Playback speed<select value={playbackRate} onChange={(event) => setPlaybackRate(event.target.value)}><option>0.8x</option><option>1.0x</option><option>1.25x</option></select></label><div className="audio-transport-buttons"><button type="button" disabled={!currentOutput} onClick={() => { if (audioRef.current) audioRef.current.currentTime = Math.max(0, audioRef.current.currentTime - 10); }}>Back 10s</button><button type="button" disabled={!currentOutput} onClick={() => { if (audioRef.current) audioRef.current.currentTime += 10; }}>Forward 10s</button></div><small>{currentOutput ? `${formatClock(currentOutput.duration)} ${currentOutput.live ? 'stitched preview' : 'rendered'}` : 'No audio loaded'}</small></div></div>
              <form className="live-command" onSubmit={(event) => { event.preventDefault(); submitLiveCommand(); }}><input value={liveCommand} onChange={(event) => setLiveCommand(event.target.value)} placeholder="Add a production note" /><button type="submit" disabled={!liveCommand.trim()}>Apply</button></form>
            </article>
            <article className="podcast-card podcast-output-panel live-output-panel"><h3>Podcast outputs</h3><div className="output-layout"><div className="cover-art">AI<br />EVERYDAY<br />LIFE</div><div className="output-copy"><h4>{title || 'Untitled episode'} <span>{connectedJob ? String(connectedJob.status).toUpperCase() : createJobMutation.isPending ? liveStatus : 'IDLE'}</span></h4><small>{formatOptions.find((option) => option.id === format)?.label} - {speakers.length} voices - {duration}</small><p>A deep dive for {audience.toLowerCase()} in a {tone.toLowerCase()} tone with transcript, chapters, and downloadable audio assets.</p>{currentOutput ? <em>{currentOutput.title}</em> : null}</div><div className="download-grid"><button type="button" disabled={!currentOutput} onClick={() => downloadCurrentOutput('MP3')}>MP3</button><button type="button" disabled={!currentOutput} onClick={() => downloadCurrentOutput('WAV')}>WAV</button><button type="button" onClick={() => setActionMessage('Transcript export requested.')}>Transcript</button><button type="button" onClick={() => setActionMessage('Show notes export requested.')}>Show Notes</button><button type="button" className="download-all" disabled={!currentOutput} onClick={() => downloadCurrentOutput('Download all')}>Download all</button><button type="button" onClick={() => void copyEpisodeLink()}>Copy link</button><button type="button" onClick={startGeneration}>Regenerate</button></div></div></article>
          </section>
          <aside className="podcast-sidebar"><article className="podcast-card recent-card collapsible-card"><div className="card-heading-row"><h3>Recent jobs</h3></div><div className="recent-job-list">{recentJobs.map((job) => <p key={`${job.id}-${job.status}`}><span className="recent-job-title" title={job.name}>{job.name}</span><OmnixStatusPill>{job.status}</OmnixStatusPill><small>{job.duration}</small><button type="button" onClick={() => selectRecentJob(job.id)}>Select</button></p>)}</div></article></aside>
        </div>
        <p className="action-toast" role="status">{actionMessage}</p>
      </div>
    </WorkspacePanel>
  );
}
