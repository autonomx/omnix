// @ts-nocheck
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useRef, useState } from 'react';
import { omnixApiClient, type AssetListResponse, type JobRecord } from '../../api/client';
import type { OmnixModuleDefinition } from '../../app/modules';
import { OmnixStatusPill, WorkspacePanel } from '../../design/primitives';
import { mockPodcastRelationships, mockPodcastSpeakerProfiles } from '../conversation-production/speakers';
import { FeatureSubmitFeedback, FeatureValidationMessage } from '../shared/FeatureSubmitFeedback';
import { mockProductionAssetTiles, mockProductionStages, mockQualityGates, mockRecentPodcastJobs, mockSessionMetrics } from './mockProduction';
import { buildReviewPolicy, generationStyleOptions, reviewStopOptions } from './reviewPolicy';
import type { PodcastFormat } from './types';
import './PodcastWorkspace.css';

type VoiceAsset = AssetListResponse['assets'][number];
type SpeakerDraft = ReturnType<typeof toSpeakerDraft>;

type SidebarPanel = 'quality' | 'health' | 'recent';

interface PlayablePodcastOutput {
  dataUrl: string;
  duration: number;
  jobId: string;
  key: string;
  title: string;
}

interface RelationshipConfig {
  hostLabel: string;
  guestALabel: string;
  guestBLabel: string;
  moderation: string;
  respect: string;
  disagreement: string;
}

const defaultTitle = 'The Future of AI in Everyday Life';
const defaultBrief = 'Explore how artificial intelligence is shaping our daily lives, transforming work and productivity, inspiring creativity, influencing relationships, and augmenting decision-making. We will discuss opportunities, risks, and what comes next.';
const defaultRelationships: RelationshipConfig = {
  hostLabel: 'Host',
  guestALabel: 'Guest A',
  guestBLabel: 'Guest B',
  moderation: 'moderates',
  respect: 'respects',
  disagreement: 'disagrees with',
};
const durationOptions = ['2 min', '5 min', '10 min', '15 min', '20 min', '30 min', '45 min', '60 min'];
const formatOptions: Array<{ id: PodcastFormat; label: string; description: string }> = [
  { id: 'debate', label: 'Debate', description: 'Two or more opposing sides' },
  { id: 'interview', label: 'Interview', description: 'Host interviews guests' },
  { id: 'speech', label: 'Speech', description: 'Solo host presentation' },
];
const terminalStatuses = ['completed', 'complete', 'succeeded', 'success', 'done', 'failed', 'error', 'cancelled', 'canceled'];
const outputSettings = { speed: 1, pitch: 0, stability: 0.72, similarity: 0.78 };
const audioEffects = ['Compression', 'De-esser'];

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

function splitTags(value: string): string[] {
  return value.split(/[,\n]/).map((tag) => tag.trim()).filter(Boolean);
}

function durationSeconds(duration: string): number {
  return Number.parseInt(duration, 10) * 60;
}

function durationClock(duration: string): string {
  return `${Number.parseInt(duration, 10)}:00`;
}

function formatClock(seconds: number): string {
  const safeSeconds = Number.isFinite(seconds) && seconds > 0 ? Math.floor(seconds) : 0;
  return `${String(Math.floor(safeSeconds / 60)).padStart(2, '0')}:${String(safeSeconds % 60).padStart(2, '0')}`;
}

function isTerminal(status: unknown): boolean {
  return terminalStatuses.includes(String(status ?? '').toLowerCase());
}

function isFailed(status: unknown): boolean {
  return ['failed', 'error', 'cancelled', 'canceled'].includes(String(status ?? '').toLowerCase());
}

function stageState(status: unknown, index: number, activeIndex: number) {
  const normalized = String(status ?? '').toLowerCase();
  if (isFailed(normalized)) return 'failed';
  if (['completed', 'complete', 'succeeded', 'success', 'done'].includes(normalized)) return 'done';
  if (['running', 'in_progress', 'active', 'processing', 'leased', 'retrying', 'queued'].includes(normalized)) return 'active';
  return index === activeIndex ? 'active' : index < activeIndex ? 'done' : 'pending';
}

function jobTitle(job: { type: string; input_payload?: unknown }): string {
  const payload = job.input_payload;
  return payload && typeof payload === 'object' && typeof (payload as { title?: unknown }).title === 'string'
    ? String((payload as { title: string }).title)
    : job.type;
}

function voiceStoragePath(asset: VoiceAsset | undefined): string {
  const value = (asset as { storage_path?: unknown } | undefined)?.storage_path;
  return typeof value === 'string' ? value : '';
}

function voiceAssetId(asset: VoiceAsset | undefined): string {
  const value = (asset as { id?: unknown } | undefined)?.id;
  return typeof value === 'string' ? value : '';
}

function voiceAssetName(asset: VoiceAsset): string {
  const metadata = (asset as { metadata?: { profile_name?: unknown; name?: unknown } }).metadata ?? {};
  const metadataName = typeof metadata.profile_name === 'string' ? metadata.profile_name : typeof metadata.name === 'string' ? metadata.name : '';
  if (metadataName.trim()) return metadataName.trim();
  const source = voiceStoragePath(asset) || voiceAssetId(asset);
  return source.split(/[\\/]/).pop()?.replace(/\.[^.]+$/, '') || voiceAssetId(asset) || 'Voice';
}

function voiceOptionsFromAssets(assets: VoiceAsset[]) {
  return assets
    .filter((asset) => asset.type === 'voice_profile')
    .map((asset) => ({ id: voiceStoragePath(asset) || voiceAssetId(asset), label: voiceAssetName(asset) }))
    .filter((voice) => voice.id);
}

function firstTag(value: string): string {
  return splitTags(value)[0] ?? 'Neutral';
}

function trimText(value: string, maxLength = 240): string {
  const text = value.replace(/\s+/g, ' ').trim();
  return text.length <= maxLength ? text : `${text.slice(0, maxLength).replace(/\s+\S*$/, '')}...`;
}

function buildPodcastSegments(title: string, brief: string, audience: string, tone: string, speakers: SpeakerDraft[]) {
  const cleanTitle = title.trim() || 'Untitled episode';
  const cleanBrief = trimText(brief || 'Discuss the topic with practical examples, risks, and a clear takeaway.');
  const host = speakers[0]?.name || 'Host';
  const guest = speakers[1]?.name || host;
  const rows = [
    { index: 0, speaker: host, text: `Welcome to ${cleanTitle}. Today we are making this useful for ${audience.toLowerCase()} in a ${tone.toLowerCase()} tone.` },
    { index: 1, speaker: guest, text: `${cleanBrief} I want to keep the discussion concrete and useful.` },
  ];
  for (const speaker of speakers.slice(0, 4)) {
    const goal = trimText(speaker.goal || speaker.instructions || speaker.identity, 180);
    if (goal) rows.push({ index: rows.length, speaker: speaker.name || host, text: goal });
  }
  rows.push({ index: rows.length, speaker: host, text: `That is the practical frame for ${cleanTitle}: use the upside, watch the failure modes, and decide what to try next.` });
  return rows;
}

function speakerCounts(segments: Array<{ speaker: string }>) {
  const counts: Record<string, number> = {};
  for (const segment of segments) counts[segment.speaker] = (counts[segment.speaker] ?? 0) + 1;
  return counts;
}

function podcastStages(segments: Array<{ speaker: string }>) {
  return [
    { id: 'producer_plan', label: 'Producer Plan', resource_class: 'cpu' as const, status: 'queued' as const },
    { id: 'performance_script', label: 'Performance Script', resource_class: 'cpu' as const, status: 'queued' as const },
    ...segments.map((segment, index) => ({ id: `voice_take_${index}`, label: `Voice Take: ${segment.speaker}`, resource_class: 'gpu:tts' as const, status: 'queued' as const })),
    { id: 'voice_takes', label: 'Voice Takes', resource_class: 'gpu:tts' as const, status: 'queued' as const },
    { id: 'mix', label: 'Mix', resource_class: 'cpu' as const, status: 'queued' as const },
    { id: 'podcast_renderer', label: 'Podcast Renderer', resource_class: 'cpu' as const, status: 'queued' as const },
  ];
}

function buildPodcastJobPayload(args: { title: string; brief: string; format: PodcastFormat; audience: string; duration: string; tone: string; language: string; generationStyle: string; reviewPolicy: unknown; speakers: SpeakerDraft[]; voiceOptions: Array<{ id: string; label: string }>; segments: Array<{ index: number; speaker: string; text: string }>; citationRequired: string; familyFriendly: string; readingLevel: string; maxTurnSeconds: string; avoidTopics: string; relationships: RelationshipConfig }) {
  const counts = speakerCounts(args.segments);
  const firstVoice = args.speakers.find((speaker) => speaker.voice)?.voice || args.voiceOptions[0]?.id || null;
  return {
    title: args.title,
    brief: args.brief,
    format: args.format,
    audience: args.audience,
    duration_minutes: Number.parseInt(args.duration, 10),
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
    character_voice_assignments: args.speakers.map((speaker, index) => ({
      speaker: speaker.name,
      voice_id: speaker.voice || args.voiceOptions[index % Math.max(args.voiceOptions.length, 1)]?.id || null,
      style: firstTag(speaker.speakingStyle || speaker.personality),
      line_count: counts[speaker.name] ?? 0,
    })),
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
    constraints: {
      maxDurationSeconds: durationSeconds(args.duration),
      targetDurationSeconds: durationSeconds(args.duration),
      maxSpeakerTurnSeconds: Number.parseInt(args.maxTurnSeconds, 10) || 45,
      citationRequired: args.citationRequired === 'On',
      familyFriendly: args.familyFriendly === 'On',
      readingLevel: args.readingLevel,
      avoidTopics: splitTags(args.avoidTopics),
      requiredTopics: ['practical examples', 'risks', 'future outlook'],
      disallowedClaims: [],
      tone: args.tone,
      audience: args.audience,
      language: args.language,
    },
  };
}

function extractPlayableOutputs(jobs: Array<JobRecord | undefined>): PlayablePodcastOutput[] {
  const outputs: PlayablePodcastOutput[] = [];
  const seen = new Set<string>();
  for (const job of jobs) {
    const refs = (job?.output_refs ?? []) as Array<{ data_url?: unknown; duration?: unknown; asset_id?: unknown; title?: unknown }>;
    for (const ref of refs) {
      const dataUrl = typeof ref.data_url === 'string' ? ref.data_url : '';
      if (!dataUrl.startsWith('data:audio/')) continue;
      const title = typeof ref.title === 'string' && ref.title.trim() ? ref.title : jobTitle(job as JobRecord);
      const key = `${job?.id ?? 'job'}:${String(ref.asset_id || title || outputs.length)}`;
      if (seen.has(key)) continue;
      seen.add(key);
      outputs.push({ dataUrl, duration: Number(ref.duration || 0), jobId: job?.id || 'job', key, title });
    }
  }
  return outputs;
}

function jobErrorMessage(job: any): string {
  if (!job || !isFailed(job.status)) return '';
  return typeof job.error?.message === 'string' ? `Podcast generation failed: ${job.error.message}` : 'Podcast generation failed.';
}

function selectFirstJobOutput(job: JobRecord, setSelectedOutputKey: (key: string) => void): void {
  const output = extractPlayableOutputs([job])[0];
  if (output) setSelectedOutputKey(output.key);
}

function safeDownloadName(value: string): string {
  return value.replace(/[^A-Za-z0-9_.-]+/g, '-').replace(/^-+|-+$/g, '') || 'podcast-output';
}

export function PodcastWorkspace({ module }: { module: OmnixModuleDefinition }) {
  const queryClient = useQueryClient();
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const jobsQuery = useQuery({ queryKey: ['platform', 'jobs'], queryFn: () => omnixApiClient.listJobs() });
  const assetsQuery = useQuery({ queryKey: ['platform', 'assets'], queryFn: () => omnixApiClient.listAssets() });
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
  const [transcript, setTranscript] = useState<Array<{ timestamp: string; speaker: string; text: string }>>([]);
  const [directorNote, setDirectorNote] = useState('No live production is running. Configure the episode, then press Generate live podcast.');
  const [directorCollapsed, setDirectorCollapsed] = useState(false);
  const [speakerMenuId, setSpeakerMenuId] = useState('');
  const [showAllRecentJobs, setShowAllRecentJobs] = useState(false);
  const [collapsedPanels, setCollapsedPanels] = useState<Record<SidebarPanel, boolean>>({ quality: false, health: false, recent: false });
  const [liveCommand, setLiveCommand] = useState('');
  const [playbackRate, setPlaybackRate] = useState('1.0x');
  const [playbackDuration, setPlaybackDuration] = useState(0);
  const [selectedOutputKey, setSelectedOutputKey] = useState('');
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
    mutationFn: () => {
      const segments = buildPodcastSegments(title, brief, audience, tone, speakers);
      return omnixApiClient.createJob({ module: 'podcast', type: 'tts.multi_speaker_synthesize', resource_class: 'gpu:tts', priority: 0, input_payload: buildPodcastJobPayload({ title, brief, format, audience, duration, tone, language, generationStyle, reviewPolicy, speakers, voiceOptions, segments, citationRequired, familyFriendly, readingLevel, maxTurnSeconds, avoidTopics, relationships }), stages: podcastStages(segments) }, { timeoutMs: 120000, timeoutMessage: 'Podcast audio generation is still running.' });
    },
    onMutate: () => {
      audioRef.current?.pause();
      setSelectedOutputKey('__pending__');
      setPlaybackDuration(0);
      setDirectorNote('Director started production through the same local TTS path used by Voice Studio.');
      setTranscript([{ timestamp: '00:00', speaker: 'Director', text: 'Production started. Building a speaker-tagged script and queueing voice takes.' }]);
      setActionMessage('Podcast production is starting...');
    },
    onSuccess: async (job) => {
      selectFirstJobOutput(job, setSelectedOutputKey);
      if (isFailed(job.status)) {
        setDirectorNote(jobErrorMessage(job));
        setActionMessage(jobErrorMessage(job));
      } else {
        setDirectorNote(`Director queued ${job.type}. Podcast audio is using Voice Library assignments.`);
        setTranscript((lines) => [...lines, { timestamp: '00:14', speaker: 'Director', text: `Job ${job.id} returned with status ${job.status}.` }]);
        setActionMessage(extractPlayableOutputs([job]).length ? `Podcast audio ready: ${job.id}` : `Podcast production queued: ${job.id}`);
      }
      await Promise.all([queryClient.invalidateQueries({ queryKey: ['platform', 'jobs'] }), queryClient.invalidateQueries({ queryKey: ['platform', 'assets'] })]);
    },
  });

  const previewVoiceMutation = useMutation({
    mutationFn: (speaker: SpeakerDraft) => omnixApiClient.createJob({ module: 'podcast', type: 'tts.synthesize', resource_class: 'gpu:tts', priority: 1, input_payload: { text: `${speaker.name}: This is a preview of ${speaker.name} for ${title}.`, title: `${speaker.name} preview`, provider_id: null, speaker: speaker.name, voice_id: speaker.voice || null, script_mode: 'single_speaker', script_speakers: [{ name: speaker.name, count: 1 }], script_segments: [{ index: 0, speaker: speaker.name, text: `This is a preview of ${speaker.name} for ${title}.` }], character_voice_assignments: [{ speaker: speaker.name, voice_id: speaker.voice || null, style: firstTag(speaker.speakingStyle), line_count: 1 }], output_settings: outputSettings, audio_effects: audioEffects, save_output: true }, stages: [{ id: 'preview_script', label: 'Prepare preview', resource_class: 'cpu', status: 'queued' }, { id: 'preview_voice', label: 'Generate preview', resource_class: 'gpu:tts', status: 'queued' }] }, { timeoutMs: 90000, timeoutMessage: 'Voice preview is still running.' }),
    onSuccess: async (job) => { selectFirstJobOutput(job, setSelectedOutputKey); setActionMessage(isFailed(job.status) ? jobErrorMessage(job) : `Voice preview ${extractPlayableOutputs([job]).length ? 'ready' : 'queued'}: ${job.id}`); await Promise.all([queryClient.invalidateQueries({ queryKey: ['platform', 'jobs'] }), queryClient.invalidateQueries({ queryKey: ['platform', 'assets'] })]); },
  });

  const podcastJobs = jobsQuery.data?.jobs.filter((job) => job.module === 'podcast') ?? [];
  const activeJob = podcastJobs.find((job) => !isTerminal(job.status));
  const connectedJob = createJobMutation.data ?? previewVoiceMutation.data ?? activeJob ?? podcastJobs[0];
  const playableOutputs = useMemo(() => extractPlayableOutputs([createJobMutation.data, previewVoiceMutation.data, ...podcastJobs]), [createJobMutation.data, podcastJobs, previewVoiceMutation.data]);
  const selectedOutput = selectedOutputKey ? playableOutputs.find((output) => output.key === selectedOutputKey) ?? null : playableOutputs[0] ?? null;
  const currentOutput = selectedOutputKey === '__pending__' || selectedOutputKey === '__new__' ? null : selectedOutput;
  const jobStages = connectedJob?.stages ?? [];
  const liveActive = createJobMutation.isPending || previewVoiceMutation.isPending || Boolean(connectedJob && !isTerminal(connectedJob.status));
  const liveStatus = createJobMutation.isPending || previewVoiceMutation.isPending ? 'QUEUEING' : connectedJob ? String(connectedJob.status).toUpperCase() : 'IDLE';
  const firstIncomplete = jobStages.findIndex((stage) => !['completed', 'done', 'success'].includes(String(stage.status).toLowerCase()));
  const activeStage = createJobMutation.isPending || previewVoiceMutation.isPending ? 0 : connectedJob ? (firstIncomplete >= 0 ? firstIncomplete : jobStages.length - 1) : -1;
  const stages = jobStages.length ? jobStages.map((stage, index) => ({ id: stage.id, label: stage.label, state: stageState(stage.status, index, activeStage) })) : mockProductionStages.map((stage) => ({ ...stage, state: 'pending' }));
  const failed = isFailed(connectedJob?.status);
  const recentJobs = podcastJobs.length ? podcastJobs.slice(0, showAllRecentJobs ? 12 : 3).map((job) => ({ id: job.id, name: jobTitle(job), status: job.status, duration })) : mockRecentPodcastJobs.map((job) => ({ ...job, id: job.name }));
  const showBriefError = brief.trim().length === 0 && createJobMutation.isIdle === false;

  useEffect(() => {
    if (!selectedOutputKey && playableOutputs.length > 0) setSelectedOutputKey(playableOutputs[0].key);
  }, [playableOutputs, selectedOutputKey]);

  useEffect(() => {
    audioRef.current?.pause();
    setPlaybackDuration(currentOutput?.duration ?? 0);
  }, [currentOutput?.key]);

  function toggleReviewStop(stopId: string) { setManualReviewStops((current) => current.includes(stopId) ? current.filter((id) => id !== stopId) : [...current, stopId]); }
  function updateSpeaker(id: string, field: string, value: string) { setSpeakers((current) => current.map((speaker) => speaker.id === id ? { ...speaker, [field]: value } : speaker)); }
  function addParticipant() { const next = speakers.length + 1; setSpeakers((current) => [...current, { id: `guest_${next}`, name: `Guest ${next}`, role: 'Guest Analyst', avatar: `G${next}`, identity: 'Guest Analyst', beliefs: '', personality: '', speakingStyle: '', goal: '', instructions: '', voice: voiceOptions[0]?.id ?? '' }]); setActionMessage('Added participant.'); }
  function removeParticipant(id: string) { if (speakers.length <= 1) { setActionMessage('Keep at least one participant.'); return; } setSpeakers((current) => current.filter((speaker) => speaker.id !== id)); setSpeakerMenuId(''); setActionMessage('Removed participant.'); }
  function duplicateParticipant(speaker: SpeakerDraft) { setSpeakers((current) => [...current, { ...speaker, id: `${speaker.id}_copy_${current.length + 1}`, name: `${speaker.name} Copy` }]); setSpeakerMenuId(''); setActionMessage(`Duplicated ${speaker.name}.`); }
  function submitLiveCommand() { const command = liveCommand.trim(); if (!command) return; if (!liveActive) { setActionMessage('Live edits apply during an active production run.'); return; } setDirectorNote(`Director applied live note: ${command}`); setTranscript((lines) => [...lines, { timestamp: '00:28', speaker: 'Director', text: command }]); setLiveCommand(''); }
  function updateRelationship(field: keyof RelationshipConfig, value: string) { setRelationships((current) => ({ ...current, [field]: value })); }
  function toggleSidebarPanel(panel: SidebarPanel) { setCollapsedPanels((current) => ({ ...current, [panel]: !current[panel] })); }

  function resetPodcast() {
    audioRef.current?.pause();
    setTitle('');
    setBrief('');
    setAudience('Software Engineers');
    setDuration('5 min');
    setTone('Professional');
    setLanguage('English (US)');
    setFormat('debate');
    setGenerationStyle('automatic');
    setManualReviewStops([]);
    setTranscript([]);
    setDirectorNote('New podcast request cleared. Add a title and brief, then generate.');
    setSelectedOutputKey('__new__');
    setPlaybackDuration(0);
    setActionMessage('New podcast ready.');
  }

  function selectRecentJob(jobId: string) {
    const output = playableOutputs.find((entry) => entry.jobId === jobId);
    if (output) { setSelectedOutputKey(output.key); setActionMessage(`Selected audio output: ${output.title}.`); return; }
    setActionMessage(`Selected job ${jobId}; no playable audio output is attached yet.`);
  }

  function downloadCurrentOutput(label = 'Podcast audio') {
    if (!currentOutput || typeof document === 'undefined') { setActionMessage('Generate podcast audio before downloading.'); return; }
    const link = document.createElement('a');
    link.href = currentOutput.dataUrl;
    link.download = `${safeDownloadName(currentOutput.title || title)}.wav`;
    link.click();
    setActionMessage(`${label}: download started.`);
  }

  async function copyEpisodeLink() {
    const link = typeof window !== 'undefined' ? `${window.location.href.split('#')[0]}#${connectedJob?.id ?? 'podcast'}` : connectedJob?.id ?? 'podcast';
    try { await navigator.clipboard?.writeText(link); setActionMessage('Podcast link copied.'); }
    catch { setActionMessage(`Podcast link: ${link}`); }
  }

  return (
    <WorkspacePanel>
      <div className="podcast-studio-shell">
        <header className="podcast-studio-header"><div><p className="eyebrow">Conversation engine</p><h2 id="module-title">{module.label}</h2><p>Create a podcast from a speaker-tagged conversation, Voice Library assignments, and the same local TTS generation path used by Voice Studio.</p></div><code>/podcast-renderer</code></header>
        <div className="podcast-studio-grid">
          <section className="podcast-studio-stack">
            <article className="podcast-card episode-setup-card"><div className="card-heading-row"><h3>1. Episode setup</h3><button className="ghost-button compact" type="button" onClick={resetPodcast}>New podcast</button></div><div className="episode-setup-grid"><div className="podcast-field-stack"><label>Topic / Episode title<input value={title} onChange={(event) => setTitle(event.target.value)} /></label><label>Episode brief<textarea rows={5} value={brief} onChange={(event) => setBrief(event.target.value)} /><small>{brief.length}/2000</small></label><label>Audience<select value={audience} onChange={(event) => setAudience(event.target.value)}><option>Software Engineers</option><option>General Public</option><option>Executives</option><option>Students</option><option>Experts</option></select></label></div><div className="podcast-config-stack"><span className="podcast-label">Podcast format</span><div className="format-card-grid">{formatOptions.map((option) => <button key={option.id} type="button" className={option.id === format ? 'selected' : undefined} onClick={() => setFormat(option.id)}><strong>{option.label}</strong><small>{option.description}</small></button>)}</div><div className="podcast-select-grid"><label>Duration<select value={duration} onChange={(event) => setDuration(event.target.value)}>{durationOptions.map((option) => <option key={option}>{option}</option>)}</select></label><label>Tone<select value={tone} onChange={(event) => setTone(event.target.value)}><option>Professional</option><option>Conversational</option><option>Humorous</option></select></label><label>Language<select value={language} onChange={(event) => setLanguage(event.target.value)}><option>English (US)</option><option>English (UK)</option></select></label></div><div className="generation-style-panel"><span className="podcast-label">Generation Style</span>{generationStyleOptions.map((option) => <label key={option.id} className={generationStyle === option.id ? 'generation-style selected' : 'generation-style'}><input type="radio" checked={generationStyle === option.id} onChange={() => setGenerationStyle(option.id)} /><span><strong>{option.label}</strong><small>{option.description}</small></span></label>)}<div className="review-stop-row">{reviewStopOptions.map((option) => <label key={option.id}><input type="checkbox" disabled={generationStyle !== 'guided'} checked={manualReviewStops.includes(option.id)} onChange={() => toggleReviewStop(option.id)} />{option.label}</label>)}</div></div></div></div></article>
            <article className="podcast-card"><div className="card-heading-row"><h3>2. Participants and voice casting</h3><small>{voiceOptions.length ? `Loaded ${voiceOptions.length} Voice Library voice${voiceOptions.length === 1 ? '' : 's'}` : 'No Voice Library voices found'}</small></div><div className="speaker-table editable-speaker-table"><div className="speaker-row speaker-header"><span>Speaker</span><span>Identity</span><span>Voice</span><span>Beliefs</span><span>Personality</span><span>Speaking style</span><span>Goal this episode</span><span>Instructions</span><span>Actions</span></div>{speakers.map((speaker) => <div className="speaker-row editable-speaker-row" key={speaker.id}><span className="speaker-cell-main"><b className={`speaker-avatar ${speaker.id}`}>{speaker.avatar}</b><span><input value={speaker.name} onChange={(event) => updateSpeaker(speaker.id, 'name', event.target.value)} /><input value={speaker.role} onChange={(event) => updateSpeaker(speaker.id, 'role', event.target.value)} /></span></span><span><input value={speaker.identity} onChange={(event) => updateSpeaker(speaker.id, 'identity', event.target.value)} /></span><span><select aria-label={`${speaker.name} voice`} value={speaker.voice} onChange={(event) => updateSpeaker(speaker.id, 'voice', event.target.value)}>{voiceOptions.map((voice) => <option key={voice.id} value={voice.id}>{voice.label}</option>)}{!voiceOptions.length ? <option value="">No cloned voices</option> : null}</select></span><span><textarea rows={2} value={speaker.beliefs} onChange={(event) => updateSpeaker(speaker.id, 'beliefs', event.target.value)} /></span><span><textarea rows={2} value={speaker.personality} onChange={(event) => updateSpeaker(speaker.id, 'personality', event.target.value)} /></span><span><textarea rows={2} value={speaker.speakingStyle} onChange={(event) => updateSpeaker(speaker.id, 'speakingStyle', event.target.value)} /></span><span><textarea rows={2} value={speaker.goal} onChange={(event) => updateSpeaker(speaker.id, 'goal', event.target.value)} /></span><span><textarea rows={2} value={speaker.instructions} onChange={(event) => updateSpeaker(speaker.id, 'instructions', event.target.value)} placeholder="Extra personality, pacing, conflict, or behavior notes" /></span><span className="speaker-preview speaker-actions"><button type="button" onClick={() => previewVoiceMutation.mutate(speaker)} disabled={!speaker.voice || previewVoiceMutation.isPending}>Preview</button><button type="button" onClick={() => removeParticipant(speaker.id)}>Remove</button><button type="button" onClick={() => setSpeakerMenuId((current) => current === speaker.id ? '' : speaker.id)}>More</button>{speakerMenuId === speaker.id ? <div className="speaker-menu"><button type="button" onClick={() => duplicateParticipant(speaker)}>Duplicate participant</button><button type="button" onClick={() => updateSpeaker(speaker.id, 'instructions', '')}>Clear instructions</button></div> : null}</span></div>)}</div><button className="ghost-button" type="button" onClick={addParticipant}>+ Add participant</button></article>
            <article className="podcast-card relationship-card"><h3>3. Relationships and constraints</h3><div className="relationship-layout"><div className="relationship-map"><b className="node host">H<span>{relationships.hostLabel}</span></b><b className="node guest-a">GA<span>{relationships.guestALabel}</span></b><b className="node guest-b">GB<span>{relationships.guestBLabel}</span></b><span className="line mod">{relationships.moderation}</span><span className="line respect">{relationships.respect}</span><span className="line disagree">{relationships.disagreement}</span></div><div className="relationship-config-grid"><label>Host label<input value={relationships.hostLabel} onChange={(event) => updateRelationship('hostLabel', event.target.value)} /></label><label>Guest A label<input value={relationships.guestALabel} onChange={(event) => updateRelationship('guestALabel', event.target.value)} /></label><label>Guest B label<input value={relationships.guestBLabel} onChange={(event) => updateRelationship('guestBLabel', event.target.value)} /></label><label>Moderator relation<input value={relationships.moderation} onChange={(event) => updateRelationship('moderation', event.target.value)} /></label><label>Respect relation<input value={relationships.respect} onChange={(event) => updateRelationship('respect', event.target.value)} /></label><label>Conflict relation<input value={relationships.disagreement} onChange={(event) => updateRelationship('disagreement', event.target.value)} /></label></div><div className="constraint-grid editable"><label><small>Max duration</small><strong>{durationClock(duration)}</strong></label><label><small>Citation required</small><select value={citationRequired} onChange={(event) => setCitationRequired(event.target.value)}><option>On</option><option>Off</option></select></label><label><small>Family friendly</small><select value={familyFriendly} onChange={(event) => setFamilyFriendly(event.target.value)}><option>On</option><option>Off</option></select></label><label><small>Reading level</small><select value={readingLevel} onChange={(event) => setReadingLevel(event.target.value)}><option>Grade 8</option><option>Grade 10</option><option>Expert</option></select></label><label><small>Max turn</small><select value={maxTurnSeconds} onChange={(event) => setMaxTurnSeconds(event.target.value)}><option value="20">20 sec</option><option value="45">45 sec</option><option value="60">60 sec</option><option value="90">90 sec</option></select></label><label><small>Avoid topics</small><input value={avoidTopics} onChange={(event) => setAvoidTopics(event.target.value)} /></label></div></div></article>
            <form className="episode-action-row" onSubmit={(event) => { event.preventDefault(); if (brief.trim()) createJobMutation.mutate(); }}><button className="ghost-button" type="button" onClick={resetPodcast}>New podcast</button><button className="podcast-generate-button" type="submit" disabled={createJobMutation.isPending}>Generate live podcast</button></form><FeatureValidationMessage show={showBriefError} message="Enter an episode brief before generating a podcast." /><FeatureSubmitFeedback error={createJobMutation.error} errorPrefix="Podcast request" isError={createJobMutation.isError} isPending={createJobMutation.isPending} jobId={createJobMutation.data?.status === 'failed' ? undefined : createJobMutation.data?.id} pendingMessage="Starting voice production" successPrefix="Podcast production queued" />
          </section>
          <section className="podcast-live-column"><article className={`podcast-card live-production-card ${liveActive ? 'streaming' : 'idle'}`}><div className="card-heading-row"><h3>Live production</h3><span className="auto-badge">{liveStatus}</span></div><div className="stage-rail">{stages.map((stage, index) => <span key={`${stage.id}-${stage.label}`} className={stage.state}>{stage.state === 'done' ? 'OK' : stage.state === 'failed' ? '!' : index + 1}<small>{stage.label}</small></span>)}</div><div className="director-note"><b>Director</b><span>{directorCollapsed ? 'Director note collapsed.' : failed ? (jobErrorMessage(connectedJob) || 'Last podcast job failed. Fix the request or regenerate to start a new live production run.') : directorNote}</span><button type="button" onClick={() => setDirectorCollapsed((value) => !value)}>{directorCollapsed ? 'Expand' : 'Collapse'}</button></div><div className={`waveform ${liveActive ? 'streaming' : 'idle'}`} aria-hidden="true">{Array.from({ length: 64 }, (_, index) => <i key={index} style={{ height: `${18 + ((index * 17 + transcript.length * 5) % 42)}px` }} />)}</div><div className="live-transcript">{transcript.length ? transcript.map((line) => <p key={`${line.timestamp}-${line.speaker}-${line.text}`}><time>{line.timestamp}</time><b>{line.speaker}</b><span>{line.text}</span></p>) : <div className="live-empty-state"><strong>{failed ? 'Production failed' : 'No live transcript yet'}</strong><span>{failed ? (jobErrorMessage(connectedJob) || 'The last podcast job reported a failure.') : 'Press Generate live podcast to start live production events.'}</span></div>}</div><div className="podcast-audio-player" aria-label="Podcast audio player"><div className="audio-player-heading"><span>{currentOutput ? currentOutput.title : 'No podcast audio yet'}</span><small>{currentOutput ? 'AUDIO READY' : 'Generate a completed podcast to enable playback'}</small></div><audio ref={audioRef} src={currentOutput?.dataUrl ?? undefined} controls preload="metadata" onLoadedMetadata={(event) => setPlaybackDuration(event.currentTarget.duration || currentOutput?.duration || 0)} onError={() => setActionMessage('The generated audio could not be loaded by the browser.')} /><div className="audio-toolbar"><label>Playback speed<select value={playbackRate} onChange={(event) => { setPlaybackRate(event.target.value); if (audioRef.current) audioRef.current.playbackRate = Number.parseFloat(event.target.value) || 1; }}><option>0.8x</option><option>1.0x</option><option>1.25x</option></select></label><small>{currentOutput ? `${formatClock(playbackDuration || currentOutput.duration)} available` : 'No audio loaded'}</small></div></div><form className="live-command" onSubmit={(event) => { event.preventDefault(); submitLiveCommand(); }}><input value={liveCommand} disabled={!liveActive} onChange={(event) => setLiveCommand(event.target.value)} placeholder={liveActive ? 'Make Guest B more skeptical' : 'Start generation to edit the live run'} /><button type="submit" disabled={!liveActive || !liveCommand.trim()}>Apply</button></form></article></section>
          <aside className="podcast-sidebar"><article className="podcast-card quality-card collapsible-card"><div className="card-heading-row"><h3>Quality gates</h3><button className="collapse-toggle" type="button" onClick={() => toggleSidebarPanel('quality')}>{collapsedPanels.quality ? 'Expand' : 'Collapse'}</button></div>{!collapsedPanels.quality ? <div className="sidebar-card-body">{mockQualityGates.map((gate) => <button type="button" key={gate.label} className={gate.status === 'Warning' ? 'warning' : undefined} onClick={() => setActionMessage(`${gate.label} gate: ${gate.status}.`)}><span>{gate.label}</span><b>{gate.status}</b></button>)}</div> : null}</article><article className="podcast-card health-card collapsible-card"><div className="card-heading-row"><h3>Session health</h3><button className="collapse-toggle" type="button" onClick={() => toggleSidebarPanel('health')}>{collapsedPanels.health ? 'Expand' : 'Collapse'}</button></div>{!collapsedPanels.health ? <div className="health-grid">{mockSessionMetrics.map((metric) => <div key={metric.label}><small>{metric.label}</small><strong>{metric.value}</strong></div>)}</div> : null}</article><article className="podcast-card recent-card collapsible-card"><div className="card-heading-row"><h3>Recent jobs</h3><span className="recent-actions"><button className="collapse-toggle" type="button" onClick={() => toggleSidebarPanel('recent')}>{collapsedPanels.recent ? 'Expand' : 'Collapse'}</button><button type="button" onClick={() => setShowAllRecentJobs((value) => !value)}>{showAllRecentJobs ? 'Show fewer' : 'View all'}</button></span></div>{!collapsedPanels.recent ? <div className="recent-job-list">{recentJobs.map((job) => <p key={`${job.id}-${job.status}`}><span className="recent-job-title" title={job.name}>{job.name}</span><OmnixStatusPill>{job.status}</OmnixStatusPill><small>{job.duration}</small><button type="button" onClick={() => selectRecentJob(job.id)}>Select</button></p>)}</div> : null}</article></aside>
        </div>
        <section className="podcast-bottom-grid"><article className="podcast-card production-assets-panel"><h3>Production assets</h3><div>{mockProductionAssetTiles.map((asset) => <section className={`asset-tile ${asset.color}`} key={asset.label}><b>{asset.label}</b><small>{asset.status}</small><button type="button" onClick={() => setActionMessage(`${asset.label}: ${asset.action} requested.`)}>{asset.action}</button></section>)}</div></article><article className="podcast-card podcast-output-panel"><h3>Podcast outputs</h3><div className="output-layout"><div className="cover-art">AI<br />EVERYDAY<br />LIFE</div><div className="output-copy"><h4>{title || 'Untitled episode'} <span>{connectedJob ? String(connectedJob.status).toUpperCase() : 'IDLE'}</span></h4><small>{formatOptions.find((option) => option.id === format)?.label} - {speakers.length} voices - {duration}</small><p>A deep dive for {audience.toLowerCase()} in a {tone.toLowerCase()} tone with transcript, citations, chapters, and downloadable audio assets.</p><b>AI</b><b>Future</b><b>Technology</b>{currentOutput ? <em>{currentOutput.title}</em> : null}</div><div className="download-grid"><button type="button" disabled={!currentOutput} onClick={() => downloadCurrentOutput('MP3')}>MP3</button><button type="button" disabled={!currentOutput} onClick={() => downloadCurrentOutput('WAV')}>WAV</button><button type="button" onClick={() => setActionMessage('Transcript export requested.')}>Transcript</button><button type="button" onClick={() => setActionMessage('Show notes export requested.')}>Show Notes</button><button type="button" className="download-all" disabled={!currentOutput} onClick={() => downloadCurrentOutput('Download all')}>Download all</button><button type="button" onClick={() => void copyEpisodeLink()}>Copy link</button><button type="button" onClick={() => createJobMutation.mutate()}>Regenerate</button></div></div></article></section>
        <p className="action-toast" role="status">{actionMessage}</p>
      </div>
    </WorkspacePanel>
  );
}
