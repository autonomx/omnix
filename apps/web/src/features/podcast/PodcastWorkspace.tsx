import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
import { omnixApiClient } from '../../api/client';
import type { OmnixModuleDefinition } from '../../app/modules';
import { OmnixStatusPill, WorkspacePanel } from '../../design/primitives';
import type { ProductionGenerationStyle, ReviewPolicy } from '../conversation-production/types';
import { mockPodcastRelationships, mockPodcastSpeakerProfiles } from '../conversation-production/speakers';
import { FeatureSubmitFeedback, FeatureValidationMessage } from '../shared/FeatureSubmitFeedback';
import type { PodcastFormat } from './types';
import {
  mockDownloadAssetTiles,
  mockProductionAssetTiles,
  mockProductionStages,
  mockQualityGates,
  mockRecentPodcastJobs,
  mockSessionMetrics,
  type MockProductionStage,
  type MockTranscriptLine,
} from './mockProduction';
import { buildReviewPolicy, generationStyleOptions, reviewStopOptions } from './reviewPolicy';
import './PodcastWorkspace.css';

interface VoiceOption { id: string; label: string; source?: string; }
interface SpeakerDraft { id: string; name: string; role: string; avatar: string; identity: string; beliefs: string; personality: string; speakingStyle: string; goal: string; instructions: string; voiceDisplayName: string; }

const formatOptions: Array<{ id: PodcastFormat; label: string; icon: string; description: string }> = [
  { id: 'debate', label: 'Debate', icon: '👥', description: 'Two or more opposing sides' },
  { id: 'interview', label: 'Interview', icon: '🎙', description: 'Host interviews guests' },
  { id: 'speech', label: 'Speech', icon: '♜', description: 'Solo host presentation' },
];
const fallbackVoiceOptions: VoiceOption[] = [
  { id: 'host_confident_calm', label: 'Host – Confident Calm', source: 'Fallback preset' },
  { id: 'dr_alex_morgan', label: 'Dr. Alex Morgan', source: 'Fallback preset' },
  { id: 'jordan_lee', label: 'Jordan Lee', source: 'Fallback preset' },
  { id: 'narrator_warm_studio', label: 'Narrator – Warm Studio', source: 'Fallback preset' },
  { id: 'analyst_crisp_focus', label: 'Analyst – Crisp Focus', source: 'Fallback preset' },
];
const liveInterventionResponses: Record<string, string> = {
  skeptical: 'Director applied live note: Guest B will challenge assumptions harder in the remaining script.',
  humorous: 'Director applied live note: remaining turns will include lighter banter while preserving the professional tone.',
  shorter: 'Director applied live note: producer will compress the remaining segments and reduce turn length.',
  examples: 'Director applied live note: writer will add more concrete examples for the selected audience.',
};
const voiceEndpoints: Array<`/api/${string}`> = ['/api/voice-studio/voices', '/api/voices', '/api/voice/voices'];

function speakerDraftFromProfile(profile: (typeof mockPodcastSpeakerProfiles)[number]): SpeakerDraft {
  return { id: profile.id, name: profile.name, role: profile.role, avatar: profile.avatar, identity: profile.identity, beliefs: profile.beliefs.join(', '), personality: profile.personality.join(', '), speakingStyle: profile.speakingStyle.join(', '), goal: profile.segmentGoals.map(({ goal }) => goal).join(' → ') || profile.defaultGoal, instructions: '', voiceDisplayName: profile.voiceMapping.voiceDisplayName };
}
function splitTags(value: string): string[] { return value.split(/[,\n]/).map((tag) => tag.trim()).filter(Boolean); }
function durationToSeconds(duration: string): number { return Number.parseInt(duration, 10) * 60; }
function durationToClock(duration: string): string { return `${Number.parseInt(duration, 10)}:00`; }
function nextTimestamp(lines: MockTranscriptLine[]): string { const last = lines.at(-1)?.timestamp ?? '00:00'; const [minutes, seconds] = last.split(':').map((part) => Number.parseInt(part, 10)); const total = minutes * 60 + seconds + 14; return `${String(Math.floor(total / 60)).padStart(2, '0')}:${String(total % 60).padStart(2, '0')}`; }
function normalizeVoicePayload(payload: unknown): VoiceOption[] {
  const records = Array.isArray(payload) ? payload : payload && typeof payload === 'object' ? Object.values(payload as Record<string, unknown>).find((value) => Array.isArray(value)) as unknown[] | undefined : undefined;
  if (!records) return [];
  return records.map((record) => {
    if (typeof record === 'string') return { id: record, label: record, source: 'Cloned voice' };
    if (!record || typeof record !== 'object') return null;
    const item = record as Record<string, unknown>;
    const id = String(item.id ?? item.voice_id ?? item.name ?? item.display_name ?? item.label ?? '').trim();
    const label = String(item.display_name ?? item.name ?? item.label ?? item.voice_id ?? item.id ?? '').trim();
    if (!id || !label) return null;
    return { id, label, source: String(item.kind ?? item.type ?? item.provider ?? 'Cloned voice') };
  }).filter((voice): voice is VoiceOption => Boolean(voice));
}
async function loadClonedVoiceOptions(): Promise<VoiceOption[]> {
  for (const endpoint of voiceEndpoints) {
    try { const voices = normalizeVoicePayload(await omnixApiClient.get<unknown>(endpoint)); if (voices.length) return voices; } catch { /* try next known voice endpoint */ }
  }
  return [];
}
function statusToStageState(status: string | undefined, index: number, activeIndex: number): MockProductionStage['state'] {
  const normalized = String(status ?? '').toLowerCase();
  if (['failed', 'error', 'cancelled', 'canceled'].includes(normalized)) return 'failed';
  if (['completed', 'complete', 'succeeded', 'success', 'done'].includes(normalized)) return 'done';
  if (['running', 'in_progress', 'active', 'processing'].includes(normalized)) return 'active';
  if (!normalized || normalized === 'queued') return index === activeIndex ? 'active' : index < activeIndex ? 'done' : 'pending';
  return index < activeIndex ? 'done' : 'pending';
}
function isTerminalStatus(status: unknown): boolean { return ['completed', 'complete', 'succeeded', 'success', 'done', 'failed', 'error', 'cancelled', 'canceled'].includes(String(status ?? '').toLowerCase()); }
function isFailedStatus(status: unknown): boolean { return ['failed', 'error', 'cancelled', 'canceled'].includes(String(status ?? '').toLowerCase()); }
function jobTitle(job: { type: string; input_payload?: unknown }): string { const payload = job.input_payload; if (payload && typeof payload === 'object' && 'title' in payload) { const title = (payload as { title?: unknown }).title; if (typeof title === 'string' && title.trim()) return title; } return job.type; }

export function PodcastWorkspace({ module }: { module: OmnixModuleDefinition }) {
  const queryClient = useQueryClient();
  const jobsQuery = useQuery({ queryKey: ['platform', 'jobs'], queryFn: () => omnixApiClient.listJobs(), refetchInterval: 3_000 });
  const clonedVoicesQuery = useQuery({ queryKey: ['podcast', 'cloned-voices'], queryFn: loadClonedVoiceOptions, staleTime: 30_000 });
  const [title, setTitle] = useState('The Future of AI in Everyday Life');
  const [brief, setBrief] = useState('Explore how artificial intelligence is shaping our daily lives, transforming work and productivity, inspiring creativity, influencing relationships, and augmenting decision-making. We’ll discuss opportunities, risks, and what comes next.');
  const [audience, setAudience] = useState('Software Engineers');
  const [duration, setDuration] = useState('20 min');
  const [tone, setTone] = useState('Professional');
  const [language, setLanguage] = useState('English (US)');
  const [format, setFormat] = useState<PodcastFormat>('debate');
  const [generationStyle, setGenerationStyle] = useState<ProductionGenerationStyle>('automatic');
  const [manualReviewStops, setManualReviewStops] = useState<Array<keyof ReviewPolicy>>([]);
  const [speakerDrafts, setSpeakerDrafts] = useState<SpeakerDraft[]>(() => mockPodcastSpeakerProfiles.map(speakerDraftFromProfile));
  const [transcriptLines, setTranscriptLines] = useState<MockTranscriptLine[]>([]);
  const [liveCommand, setLiveCommand] = useState('');
  const [directorNote, setDirectorNote] = useState('No live production is running. Configure the episode, then press Generate live podcast.');
  const [isPlaying, setIsPlaying] = useState(false);
  const [playbackRate, setPlaybackRate] = useState('1.0x');
  const [actionMessage, setActionMessage] = useState('Ready for automatic production.');
  const reviewPolicy = buildReviewPolicy(generationStyle, generationStyle === 'guided' ? manualReviewStops : []);
  const clonedVoiceOptions = useMemo(() => { const loaded = clonedVoicesQuery.data ?? []; return loaded.length ? loaded : fallbackVoiceOptions; }, [clonedVoicesQuery.data]);

  const createJobMutation = useMutation({
    mutationFn: () => omnixApiClient.createJob({
      module: 'podcast', type: 'podcast.generate', resource_class: 'gpu:llm', priority: 0,
      input_payload: {
        title, brief, format, audience, duration_minutes: Number.parseInt(duration, 10), tone, language, generation_style: generationStyle, review_policy: reviewPolicy, renderer: 'podcast',
        speakers: speakerDrafts.map((speaker) => ({ id: speaker.id, name: speaker.name, role: speaker.role, avatar: speaker.avatar, identity: speaker.identity, beliefs: splitTags(speaker.beliefs), personality: splitTags(speaker.personality), speakingStyle: splitTags(speaker.speakingStyle), defaultGoal: speaker.goal, speakerInstructions: speaker.instructions, voiceMapping: { speakerId: speaker.id, voiceId: speaker.voiceDisplayName, voiceDisplayName: speaker.voiceDisplayName, previewAvailable: true } })),
        relationships: mockPodcastRelationships,
        constraints: { maxDurationSeconds: durationToSeconds(duration), targetDurationSeconds: durationToSeconds(duration), maxSpeakerTurnSeconds: 45, citationRequired: true, familyFriendly: true, readingLevel: 'Grade 8', avoidTopics: ['Politics'], requiredTopics: ['practical examples', 'risks', 'future outlook'], disallowedClaims: [], tone, audience, language },
        prompt_template_id: 'conversation.production.podcast.v1',
      },
      stages: mockProductionStages.map((stage) => ({ id: String(stage.id), label: stage.label, resource_class: stage.id === 'voice_takes' ? 'gpu:tts' : stage.id === 'mix' || stage.id === 'podcast_renderer' ? 'cpu' : 'gpu:llm', status: 'queued' })),
    }),
    onMutate: () => { setIsPlaying(true); setDirectorNote('Director started production. Research is queued and the live panel is waiting for job updates.'); setTranscriptLines([{ timestamp: '00:00', speaker: 'Director', text: 'Production started. Waiting for Research stage events.' }]); setActionMessage('Podcast production is starting…'); },
    onSuccess: async (job) => { setDirectorNote(`Director queued ${job.type}. Live production is tracking job ${job.id}.`); setTranscriptLines((lines) => [...lines, { timestamp: nextTimestamp(lines), speaker: 'Director', text: `Job ${job.id} queued. Stage updates will appear as the backend reports progress.` }]); setActionMessage('Podcast production queued and connected to the live panel.'); await queryClient.invalidateQueries({ queryKey: ['platform', 'jobs'] }); },
    onError: () => { setIsPlaying(false); setDirectorNote('Podcast job creation failed. Update the request and try again.'); setTranscriptLines((lines) => [...lines, { timestamp: nextTimestamp(lines), speaker: 'Director', text: 'Job creation failed before live production could start.' }]); },
  });

  const podcastJobs = jobsQuery.data?.jobs.filter((job) => job.module === 'podcast') ?? [];
  const activePodcastJob = podcastJobs.find((job) => !isTerminalStatus(job.status));
  const connectedJob = createJobMutation.data ?? activePodcastJob ?? podcastJobs[0];
  const connectedJobStages = connectedJob?.stages ?? [];
  const connectedJobFailed = isFailedStatus(connectedJob?.status);
  const liveProductionActive = createJobMutation.isPending || Boolean(connectedJob && !isTerminalStatus(connectedJob.status));
  const livePanelStatus = createJobMutation.isPending ? 'QUEUEING' : connectedJob ? String(connectedJob.status).toUpperCase() : 'IDLE';
  const firstIncompleteStage = connectedJobStages.findIndex((stage) => !['completed', 'done', 'success'].includes(String(stage.status).toLowerCase()));
  const activeStageIndex = createJobMutation.isPending ? 0 : connectedJob ? (firstIncompleteStage >= 0 ? firstIncompleteStage : connectedJobStages.length - 1) : -1;
  const productionStages = connectedJobStages.length ? connectedJobStages.map((stage, index) => ({ id: String(stage.id) as MockProductionStage['id'], label: stage.label, state: statusToStageState(stage.status, index, activeStageIndex) })) : mockProductionStages.map((stage) => ({ ...stage, state: 'pending' as const }));
  const recentJobs = podcastJobs.length ? podcastJobs.slice(0, 3).map((job) => ({ name: jobTitle(job), status: job.status, duration })) : mockRecentPodcastJobs;
  const showBriefError = brief.trim().length === 0 && createJobMutation.isIdle === false;
  const effectiveDirectorNote = connectedJobFailed ? 'Last podcast job failed. Fix the request or regenerate to start a new live production run.' : directorNote;

  function voiceChoicesFor(selectedVoice: string): VoiceOption[] { return clonedVoiceOptions.some((voice) => voice.label === selectedVoice) ? clonedVoiceOptions : [{ id: selectedVoice, label: selectedVoice, source: 'Selected voice' }, ...clonedVoiceOptions]; }
  function toggleReviewStop(stopId: keyof ReviewPolicy) { setManualReviewStops((current) => (current.includes(stopId) ? current.filter((id) => id !== stopId) : [...current, stopId])); }
  function updateSpeaker(id: string, field: keyof SpeakerDraft, value: string) { setSpeakerDrafts((speakers) => speakers.map((speaker) => speaker.id === id ? { ...speaker, [field]: value } : speaker)); }
  function addParticipant() { const nextIndex = speakerDrafts.length + 1; setSpeakerDrafts((speakers) => [...speakers, { id: `guest_${nextIndex}`, name: `Guest ${String.fromCharCode(64 + nextIndex)}`, role: 'Guest Analyst', avatar: `G${String.fromCharCode(64 + nextIndex)}`, identity: 'Guest Analyst', beliefs: '', personality: '', speakingStyle: '', goal: '', instructions: '', voiceDisplayName: clonedVoiceOptions[0]?.label ?? 'Select cloned voice' }]); }
  function handleVoicePreview(speakerName: string) { setDirectorNote(`Voice preview requested for ${speakerName}. The selected cloned voice is staged for this participant.`); setActionMessage(`Previewing voice for ${speakerName}.`); }
  function handleLiveCommandSubmit() { const command = liveCommand.trim(); if (!command) return; if (!liveProductionActive) { setActionMessage('Live edits apply during an active production run. Press Generate live podcast first.'); return; } const lowered = command.toLowerCase(); const response = Object.entries(liveInterventionResponses).find(([keyword]) => lowered.includes(keyword))?.[1] ?? `Director applied live note: ${command}`; setDirectorNote(response); setTranscriptLines((lines) => [...lines, { timestamp: nextTimestamp(lines), speaker: 'Director', text: response }]); setActionMessage('Live intervention applied to the remaining production run.'); setLiveCommand(''); }
  function handleCopyLink() { if (typeof navigator !== 'undefined' && navigator.clipboard) void navigator.clipboard.writeText(`${window.location.origin}/podcast`); setActionMessage('Podcast link copied.'); }
  function handleAssetAction(asset: string, action: string) { setActionMessage(`${asset}: ${action} requested.`); }
  const reviewModeBadge = generationStyle === 'automatic' ? 'Auto-approved' : `${manualReviewStops.length || 0} review stop${manualReviewStops.length === 1 ? '' : 's'}`;

  return (
    <WorkspacePanel>
      <div className="podcast-studio-shell">
        <header className="podcast-studio-header"><div><p className="eyebrow">Conversation engine</p><h2 id="module-title">{module.label}</h2><p>Create a podcast by generating a conversation. Research, plan, write, perform, and render automatically — with full studio control when you want it.</p></div><code>/podcast-renderer</code></header>
        <div className="podcast-studio-grid">
          <section className="podcast-studio-stack">
            <article className="podcast-card episode-setup-card"><h3>▣ 1. Episode setup</h3><div className="episode-setup-grid"><div className="podcast-field-stack"><label>Topic / Episode title<input value={title} onChange={(event) => setTitle(event.target.value)} /></label><label>Episode brief<textarea rows={5} value={brief} onChange={(event) => setBrief(event.target.value)} /><small>{brief.length}/2000</small></label><label>Audience<select value={audience} onChange={(event) => setAudience(event.target.value)}><option>Software Engineers</option><option>General Public</option><option>Executives</option><option>Students</option><option>Experts</option></select></label></div><div className="podcast-config-stack"><span className="podcast-label">Podcast format</span><div className="format-card-grid">{formatOptions.map((option) => <button key={option.id} type="button" className={option.id === format ? 'selected' : undefined} onClick={() => setFormat(option.id)}><span>{option.icon}</span><strong>{option.label}</strong><small>{option.description}</small></button>)}</div><div className="podcast-select-grid"><label>Duration<select value={duration} onChange={(event) => setDuration(event.target.value)}><option>20 min</option><option>45 min</option><option>60 min</option></select></label><label>Tone<select value={tone} onChange={(event) => setTone(event.target.value)}><option>Professional</option><option>Conversational</option><option>Humorous</option></select></label><label>Language<select value={language} onChange={(event) => setLanguage(event.target.value)}><option>English (US)</option><option>English (UK)</option></select></label></div><div className="generation-style-panel"><span className="podcast-label">Generation Style ⓘ</span>{generationStyleOptions.map((option) => <label key={option.id} className={generationStyle === option.id ? 'generation-style selected' : 'generation-style'}><input type="radio" checked={generationStyle === option.id} onChange={() => setGenerationStyle(option.id)} /><span><strong>{option.label}</strong><small>{option.description}</small></span></label>)}<div className="review-stop-row" aria-label="Guided review stops">{reviewStopOptions.map((option) => <label key={option.id} title={option.description}><input type="checkbox" disabled={generationStyle !== 'guided'} checked={manualReviewStops.includes(option.id)} onChange={() => toggleReviewStop(option.id)} />{option.label}</label>)}</div></div></div></div></article>
            <article className="podcast-card"><div className="card-heading-row"><h3>⚭ 2. Participants & voice casting</h3><small>{clonedVoicesQuery.data?.length ? 'Loaded cloned voices' : 'Using fallback voice presets until cloned voices are available'}</small></div><div className="speaker-table editable-speaker-table" role="table" aria-label="Podcast participants and voice casting"><div className="speaker-row speaker-header" role="row"><span>Speaker</span><span>Identity</span><span>Beliefs</span><span>Personality</span><span>Speaking style</span><span>Goal this episode</span><span>Instructions</span><span>Cloned voice</span><span>Preview</span></div>{speakerDrafts.map((speaker) => <div className="speaker-row editable-speaker-row" role="row" key={speaker.id}><span className="speaker-cell-main"><b className={`speaker-avatar ${speaker.id}`}>{speaker.avatar}</b><span><input value={speaker.name} onChange={(event) => updateSpeaker(speaker.id, 'name', event.target.value)} aria-label={`${speaker.name} name`} /><input value={speaker.role} onChange={(event) => updateSpeaker(speaker.id, 'role', event.target.value)} aria-label={`${speaker.name} role`} /></span></span><span><input value={speaker.identity} onChange={(event) => updateSpeaker(speaker.id, 'identity', event.target.value)} aria-label={`${speaker.name} identity`} /></span><span><textarea rows={2} value={speaker.beliefs} onChange={(event) => updateSpeaker(speaker.id, 'beliefs', event.target.value)} placeholder="Optimistic, Tech-first" aria-label={`${speaker.name} beliefs`} /></span><span><textarea rows={2} value={speaker.personality} onChange={(event) => updateSpeaker(speaker.id, 'personality', event.target.value)} placeholder="Warm, Direct" aria-label={`${speaker.name} personality`} /></span><span><textarea rows={2} value={speaker.speakingStyle} onChange={(event) => updateSpeaker(speaker.id, 'speakingStyle', event.target.value)} placeholder="Conversational, Punchy" aria-label={`${speaker.name} speaking style`} /></span><span><textarea rows={2} value={speaker.goal} onChange={(event) => updateSpeaker(speaker.id, 'goal', event.target.value)} placeholder="Educate → Defend" aria-label={`${speaker.name} goal`} /></span><span><textarea rows={2} value={speaker.instructions} onChange={(event) => updateSpeaker(speaker.id, 'instructions', event.target.value)} placeholder="Extra personality, pacing, conflict, or behavior notes…" aria-label={`${speaker.name} instructions`} /></span><span><select value={speaker.voiceDisplayName} onChange={(event) => updateSpeaker(speaker.id, 'voiceDisplayName', event.target.value)}>{voiceChoicesFor(speaker.voiceDisplayName).map((voice) => <option key={`${speaker.id}-${voice.id}`} value={voice.label}>{voice.label}{voice.source ? ` · ${voice.source}` : ''}</option>)}</select></span><span className="speaker-preview"><button type="button" onClick={() => handleVoicePreview(speaker.name)}>▥</button><button type="button" onClick={() => setActionMessage(`${speaker.name} actions opened.`)}>⋮</button></span></div>)}</div><button className="ghost-button" type="button" onClick={addParticipant}>+ Add participant</button></article>
            <article className="podcast-card relationship-card"><h3>⌁ 3. Relationships & constraints</h3><div className="relationship-layout"><div className="relationship-map" aria-label="Guest relationship map"><b className="node host">H<span>Host</span></b><b className="node guest-a">GA<span>Guest A</span></b><b className="node guest-b">GB<span>Guest B</span></b><span className="line mod">moderates</span><span className="line respect">respects</span><span className="line disagree">disagrees with</span></div><div className="constraint-grid">{[['Max duration', durationToClock(duration)], ['Citation required', 'On'], ['Family friendly', 'On'], ['Reading level', 'Grade 8'], ['Max turn', '45 sec'], ['Avoid topics', 'Politics']].map(([label, value]) => <div key={label}><small>{label}</small><strong>{value}</strong></div>)}</div></div></article>
            <form onSubmit={(event) => { event.preventDefault(); if (brief.trim()) createJobMutation.mutate(); }}><button className="podcast-generate-button" type="submit" disabled={createJobMutation.isPending}>✧ {createJobMutation.isPending ? 'Generating live podcast…' : 'Generate live podcast'}</button></form><FeatureValidationMessage show={showBriefError} message="Enter an episode brief before generating a podcast." /><FeatureSubmitFeedback error={createJobMutation.error} errorPrefix="Podcast request" isError={createJobMutation.isError} isPending={createJobMutation.isPending} jobId={createJobMutation.data?.id} pendingMessage="Starting conversation production…" successPrefix="Podcast production queued" />
          </section>
          <section className="podcast-live-column"><article className={`podcast-card live-production-card ${liveProductionActive ? 'streaming' : 'idle'}`}><div className="card-heading-row"><h3>◌ Live production</h3><span className="auto-badge">{livePanelStatus}</span></div><div className="stage-rail">{productionStages.map((stage, index) => <span key={`${stage.id}-${stage.label}`} className={stage.state}>{stage.state === 'done' ? '✓' : stage.state === 'failed' ? '!' : index + 1}<small>{stage.label}</small></span>)}</div><div className="director-note"><b>Director</b><span>{effectiveDirectorNote}</span><button type="button" onClick={() => setActionMessage('Director details toggled.')}>⌄</button></div><div className={`waveform ${liveProductionActive ? 'streaming' : 'idle'}`} aria-hidden="true">{Array.from({ length: 64 }, (_, index) => <i key={index} style={{ height: `${18 + ((index * 17 + transcriptLines.length * 5) % 42)}px` }} />)}</div><div className="live-transcript">{transcriptLines.length ? transcriptLines.map((line) => <p key={`${line.timestamp}-${line.speaker}-${line.text}`}><time>{line.timestamp}</time><b>{line.speaker}</b><span>{line.text}</span></p>) : <div className="live-empty-state"><strong>{connectedJobFailed ? 'Production failed' : 'No live transcript yet'}</strong><span>{connectedJobFailed ? 'The last podcast job reported a failure. Regenerate to start a clean live run.' : 'Press Generate live podcast to start Research, Producer Plan, Script, Voice Takes, Mix, and Renderer events.'}</span></div>}</div><div className="playback-row"><button type="button" disabled={!liveProductionActive} onClick={() => setIsPlaying((playing) => !playing)}>{isPlaying ? 'Ⅱ' : '▶'}</button><span>▁▁▁▁▁▁</span><strong>06:42 / {durationToClock(duration)}</strong><select value={playbackRate} onChange={(event) => setPlaybackRate(event.target.value)}><option>0.8x</option><option>1.0x</option><option>1.25x</option></select><small>{livePanelStatus} ▥</small></div><form className="live-command" onSubmit={(event) => { event.preventDefault(); handleLiveCommandSubmit(); }}><input value={liveCommand} disabled={!liveProductionActive} onChange={(event) => setLiveCommand(event.target.value)} placeholder={liveProductionActive ? 'Make Guest B more skeptical…' : 'Start generation to edit the live run…'} /><button type="submit" disabled={!liveProductionActive || !liveCommand.trim()}>▷</button></form></article></section>
          <aside className="podcast-sidebar"><article className="podcast-card quality-card"><h3>🛡 Quality gates</h3>{mockQualityGates.map((gate) => <button type="button" key={gate.label} className={gate.status === 'Warning' ? 'warning' : undefined} onClick={() => setActionMessage(`${gate.label} gate: ${gate.status}.`)}><span>{gate.label}</span><b>{gate.status}</b></button>)}</article><article className="podcast-card health-card"><h3>♡ Session health</h3>{mockSessionMetrics.map((metric) => <div key={metric.label}><small>{metric.label}</small><strong>{metric.value}</strong></div>)}</article><article className="podcast-card recent-card"><div className="card-heading-row"><h3>◴ Recent jobs</h3><button type="button" onClick={() => setActionMessage('Recent jobs view requested.')}>View all</button></div>{recentJobs.map((job) => <p key={`${job.name}-${job.status}`}><span>{job.name}</span><OmnixStatusPill>{job.status}</OmnixStatusPill><small>{job.duration}</small><button type="button" onClick={() => setActionMessage(`${job.name} selected.`)}>▶</button></p>)}</article></aside>
        </div>
        <section className="podcast-bottom-grid"><article className="podcast-card production-assets-panel"><h3>▣ Production assets ⓘ</h3><div>{mockProductionAssetTiles.map((asset) => <section className={`asset-tile ${asset.color}`} key={asset.label}><b>{asset.label}</b><small>{asset.status}</small><button type="button" onClick={() => handleAssetAction(asset.label, asset.action)}>{asset.action}</button></section>)}</div></article><article className="podcast-card podcast-output-panel"><h3>⚙ Podcast outputs ⓘ</h3><div className="output-layout"><div className="cover-art">AI<br />EVERYDAY<br />LIFE</div><div className="output-copy"><h4>{title || 'Untitled episode'} <span>{connectedJob ? String(connectedJob.status).toUpperCase() : 'IDLE'}</span></h4><small>{formatOptions.find((option) => option.id === format)?.label} • {speakerDrafts.length} voices • {duration}</small><p>A deep dive for {audience.toLowerCase()} in a {tone.toLowerCase()} tone — with transcript, citations, chapters, and downloadable audio assets.</p><b>AI</b><b>Future</b><b>Technology</b></div><div className="download-grid">{mockDownloadAssetTiles.map((asset) => <button key={asset.label} type="button" onClick={() => handleAssetAction(asset.label, 'Download')}><span>{asset.icon}</span><strong>{asset.label}</strong><small>{asset.metadata}</small></button>)}<button type="button" className="download-all" onClick={() => setActionMessage('Download all requested.')}>Download all ⇩</button><button type="button" onClick={handleCopyLink}>Copy link</button><button type="button" onClick={() => createJobMutation.mutate()}>Regenerate</button></div></div></article></section>
        <p className="action-toast" role="status">{actionMessage}</p>
      </div>
    </WorkspacePanel>
  );
}
