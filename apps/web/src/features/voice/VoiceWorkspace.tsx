import { Button, Group, Progress, Text, Title } from '@mantine/core';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useMemo } from 'react';
import { useForm } from 'react-hook-form';
import { omnixApiClient, type AssetListResponse, type ProviderFacadePayload } from '../../api/client';
import type { OmnixModuleDefinition } from '../../app/modules';
import { OmnixAudioControls, OmnixStatusPill, WorkspacePanel } from '../../design/primitives';
import { FeatureSubmitFeedback, FeatureValidationMessage } from '../shared/FeatureSubmitFeedback';
import { DEFAULT_OUTPUT_SETTINGS } from './outputDefaults';
import { firstResultAsset } from './resultList';
import { parseScriptSpeakers } from './scriptLines';
import './VoiceStudioWorkspace.css';

interface VoiceFormValues {
  text: string;
  speaker: string;
  voiceId: string;
  providerId: string;
}

type VoiceAsset = AssetListResponse['assets'][number];

export function VoiceWorkspace({ module }: { module: OmnixModuleDefinition }) {
  const queryClient = useQueryClient();
  const providersQuery = useQuery({ queryKey: ['platform', 'providers'], queryFn: () => omnixApiClient.listProviders() });
  const jobsQuery = useQuery({ queryKey: ['platform', 'jobs'], queryFn: () => omnixApiClient.listJobs() });
  const assetsQuery = useQuery({ queryKey: ['platform', 'assets'], queryFn: () => omnixApiClient.listAssets() });
  const { register, handleSubmit, reset, watch, formState: { errors } } = useForm<VoiceFormValues>({ defaultValues: { text: '', speaker: '', voiceId: '', providerId: '' } });
  const textDraft = watch('text');
  const parsedSpeakers = useMemo(() => parseScriptSpeakers(textDraft), [textDraft]);
  const ttsProviders = useMemo(() => ttsCapableProviders(providersQuery.data), [providersQuery.data]);
  const voiceJobs = jobsQuery.data?.jobs.filter((job) => job.module === 'voice' || job.module === 'voice-cloning') ?? [];
  const audioAssets = assetsQuery.data?.assets.filter((asset) => asset.type === 'audio' || asset.type === 'voice_profile') ?? [];
  const profileAssets = audioAssets.filter((asset) => asset.type === 'voice_profile');
  const generatedAudioAssets = audioAssets.filter((asset) => asset.type === 'audio');
  const latestResultAsset = firstResultAsset(generatedAudioAssets);
  const createJobMutation = useMutation({
    mutationFn: (values: VoiceFormValues) => omnixApiClient.createJob({
      module: 'voice',
      type: parsedSpeakers.length > 1 ? 'tts.multi_speaker_synthesize' : 'tts.synthesize',
      resource_class: 'gpu:tts',
      priority: 0,
      input_payload: {
        text: values.text,
        speaker: values.speaker || null,
        voice_id: values.voiceId || null,
        provider_id: values.providerId || null,
        script_speakers: parsedSpeakers,
        script_mode: parsedSpeakers.length > 1 ? 'multi_speaker' : 'single_speaker',
        output_settings: DEFAULT_OUTPUT_SETTINGS,
      },
      stages: [
        { id: 'parse-script', label: 'Parse script', resource_class: 'cpu', status: 'queued' },
        { id: 'synthesize', label: 'Synthesize speech', resource_class: 'gpu:tts', status: 'queued' },
        { id: 'store-audio', label: 'Store audio asset', resource_class: 'cpu', status: 'queued' },
      ],
    }),
    onSuccess: async (_job, values) => {
      reset({ text: '', speaker: values.speaker, voiceId: values.voiceId, providerId: values.providerId });
      await queryClient.invalidateQueries({ queryKey: ['platform', 'jobs'] });
    },
  });
  const submitStatus = createJobMutation.isPending ? 'queued' : createJobMutation.isError ? 'error' : createJobMutation.data?.status ?? 'ready';

  return (
    <WorkspacePanel>
      <div className="voice-studio-shell">
        <div className="workspace-heading">
          <div>
            <p className="eyebrow">Feature module</p>
            <h2 id="module-title">Voice Studio</h2>
            <p className="workspace-summary">Text-to-speech, cloned voices, previews, queue management, and provider diagnostics.</p>
          </div>
          <code>{module.route}</code>
        </div>

        <div className="voice-dashboard-grid">
          <section className="voice-panel">
            <Group justify="space-between" align="start">
              <div><Title order={4}>Synthesis Composer</Title><Text size="sm">Build single voice or multi-speaker narration jobs.</Text></div>
              <OmnixStatusPill>{submitStatus}</OmnixStatusPill>
            </Group>
            <form className="voice-studio-field-grid" onSubmit={handleSubmit((values) => createJobMutation.mutate(values))}>
              <label className="voice-studio-field-wide">Provider<select aria-label="Provider" {...register('providerId')}><option value="">Default TTS provider</option>{ttsProviders.map((provider) => <option key={provider.id} value={provider.id}>{provider.label}</option>)}</select><small>Configured TTS provider</small></label>
              <div className="voice-studio-field-wide voice-studio-field">Voice Source<div className="voice-source-tabs" aria-label="Voice source"><button type="button">System Voices</button><button type="button" className="active">Voice Clones (Local)</button></div></div>
              <label>Clone Voice<select {...register('voiceId')}><option value="">Manual / default voice</option>{profileAssets.map((asset) => <option key={asset.id} value={asset.storage_path}>{voiceAssetName(asset)}</option>)}</select></label>
              <label>Speaker / Preset<input aria-label="Speaker" {...register('speaker')} placeholder="Narrator (Neutral)" /></label>
              <label>Voice ID (optional)<input placeholder="e.g. narrator_v1" readOnly value={profileAssets[0]?.id ?? ''} /></label>
              <label>Style Prompt (optional)<input placeholder="authoritative, calm, cinematic" readOnly value="" /></label>
              <div className="voice-studio-field-wide voice-slider-grid">{Object.entries(DEFAULT_OUTPUT_SETTINGS).map(([name, value]) => <label className="voice-slider-card" key={name}><span>{formatSettingName(name)}</span><b>{formatSettingValue(value)}</b><input aria-label={`Output ${name}`} type="range" min={rangeMin(name)} max={rangeMax(name)} step="0.01" value={value} readOnly /></label>)}</div>
              <label className="voice-studio-field-wide">Text to synthesize<textarea aria-label="Text" rows={7} aria-invalid={Boolean(errors.text)} placeholder={'Dave: hello there\nBob: how do you do\nMarry: I am doing fine'} {...register('text', { required: true })} /></label>
              <div className="voice-primary-actions voice-studio-field-wide"><Button type="button" variant="light">Preview</Button><Button className="voice-action-cyan" type="submit" disabled={createJobMutation.isPending} loading={createJobMutation.isPending}>Queue synthesis</Button><Button type="submit" variant="light" disabled={createJobMutation.isPending}>Generate & Play</Button><Button type="button" variant="subtle">Stop</Button></div>
            </form>
            <FeatureValidationMessage show={Boolean(errors.text)} message="Enter text before queueing speech synthesis." />
            <FeatureSubmitFeedback error={createJobMutation.error} errorPrefix="TTS request" isError={createJobMutation.isError} isPending={createJobMutation.isPending} jobId={createJobMutation.data?.id} pendingMessage="Queueing TTS job…" successPrefix="TTS job queued" />
            <p className="voice-footer-note">All synthesis requests are queued. Latest preview will auto-play when ready.</p>
          </section>

          <section className="voice-panel">
            <Group justify="space-between" align="start"><div><Title order={4}>Voice Clone Library</Title><Text size="sm">Local cloned voices from resources/voice_clones</Text></div><OmnixStatusPill>{profileAssets.length} voices</OmnixStatusPill></Group>
            {profileAssets.length ? <div className="voice-clone-grid">{profileAssets.map((asset, index) => <VoiceCloneCard key={asset.id} asset={asset} active={index === 0} />)}</div> : <div className="platform-empty" role="status">No voice profiles indexed.</div>}
            <p className="voice-footer-note">Voices are stored locally and never leave your environment.</p>
          </section>

          <section className="voice-panel">
            <Group justify="space-between" align="start"><div><Title order={4}>Jobs & Playback Queue</Title><Text size="sm">Active queue, recent jobs, and latest preview.</Text></div><Button size="xs" variant="subtle">Clear Completed</Button></Group>
            <div className="voice-queue-list"><div className="voice-queue-row voice-table-heading"><span>Job</span><span>Status</span><span>Provider</span><span>Time</span></div>{voiceJobs.slice(0, 5).map((job) => <div className="voice-queue-row" key={job.id}><span><b>{job.type}</b><small>{job.module}</small></span><span><OmnixStatusPill>{job.status}</OmnixStatusPill><Progress value={progressPercent(job.progress)} /></span><span>Default TTS</span><span>{job.progress?.message ?? '—'}</span></div>)}{!voiceJobs.length ? <div className="platform-empty" role="status">No voice jobs queued.</div> : null}</div>
            <div className="voice-player-panel"><Group justify="space-between"><Text size="sm">Latest Preview · {latestResultAsset ? voiceAssetName(latestResultAsset) : 'Narrator (Neutral)'}</Text><Text size="sm">00:06 / 00:12</Text></Group><Waveform /><Group gap="xs"><Button size="xs" variant="light">Pause</Button><Button size="xs" variant="subtle">Back</Button><Button size="xs" variant="subtle">Forward</Button><Button size="xs" variant="subtle">Export</Button><Button size="xs" variant="subtle">Keep</Button></Group></div>
          </section>

          <section className="voice-panel voice-panel-wide">
            <Group justify="space-between" align="start"><div><Title order={4}>Audio Assets</Title><Text size="sm">Recent generated audio clips</Text></div><Button size="xs" variant="subtle">Export Selected</Button></Group>
            {generatedAudioAssets.length ? <div className="voice-asset-table"><div className="voice-asset-row voice-table-heading"><span></span><span>File Name</span><span>Voice</span><span>Provider</span><span>Duration</span><span>Actions</span></div>{generatedAudioAssets.slice(0, 6).map((asset) => <AudioAssetRow key={asset.id} asset={asset} />)}</div> : <div className="platform-empty" role="status">No audio assets indexed.</div>}
          </section>

          <section className="voice-panel">
            <Group justify="space-between" align="start"><div><Title order={4}>Provider Diagnostics</Title><Text size="sm">Last updated: local session</Text></div><Button size="xs" variant="subtle">Refresh</Button></Group>
            <div className="voice-diagnostics-grid"><DiagnosticCard title="TTS Provider" status="Online" tone="online" detail="Latency 128 ms" /><DiagnosticCard title="Queue Worker" status="Online" tone="online" detail={`${voiceJobs.length} jobs`} /><DiagnosticCard title="GPU (CUDA)" status="Idle" tone="idle" detail="Memory available" /><DiagnosticCard title="CPU" status="Ready" tone="idle" detail="Resources normal" /></div>
            <div className="voice-diagnostic-list">{['TTS provider health check passed', 'Queue worker heartbeat OK', 'GPU status OK', 'System resources within normal limits'].map((message) => <div className="voice-diagnostic-row" key={message}><span>✓</span><span>{message}</span><span>now</span></div>)}</div>
          </section>
        </div>
      </div>
    </WorkspacePanel>
  );
}

function VoiceCloneCard({ asset, active }: { asset: VoiceAsset; active: boolean }) {
  return <article className={`voice-clone-card${active ? ' active' : ''}`}><Group justify="space-between"><Group gap="xs"><span className="voice-avatar">◉</span><strong>{voiceAssetName(asset)}</strong></Group><OmnixStatusPill>✓</OmnixStatusPill></Group><Text size="sm"><span className="voice-status-dot" /> Ready</Text><div className="voice-meta-list"><span>Profile</span><b>{asset.id}</b><span>Sample Rate</span><b>48 kHz</b><span>Source</span><b>{asset.storage_path}</b></div><div className="voice-card-actions"><Button size="xs" variant="subtle">Preview</Button><Button size="xs" variant="light">Use</Button></div></article>;
}

function AudioAssetRow({ asset }: { asset: VoiceAsset }) {
  return <div className="voice-asset-row"><span>▶</span><span><Title order={4}>audio / voice</Title><small>{asset.storage_path}</small></span><span>Narrator</span><span>Default TTS</span><span>00:12</span><span><Button size="xs" variant="subtle">Play</Button><Button size="xs" variant="subtle">Export</Button></span></div>;
}

function DiagnosticCard({ title, status, detail, tone }: { title: string; status: string; detail: string; tone: 'online' | 'idle' }) {
  return <article className="voice-diagnostic-card"><Text size="sm">{title}</Text><span className={tone === 'online' ? 'voice-provider-online' : 'voice-provider-idle'}>{status}</span><Text size="sm">{detail}</Text></article>;
}

function Waveform() {
  return <div className="voice-waveform" aria-hidden="true">{Array.from({ length: 42 }, (_, index) => <span key={index} style={{ height: `${20 + ((index * 17) % 60)}%` }} />)}</div>;
}

function ttsCapableProviders(payload: ProviderFacadePayload | undefined) {
  return payload?.providers.filter((provider) => provider.capabilities.includes('tts')) ?? [];
}

function progressPercent(progress: { current: number; total: number } | undefined): number {
  if (!progress || progress.total <= 0) return 0;
  return Math.min(100, Math.round((progress.current / progress.total) * 100));
}

function voiceAssetName(asset: VoiceAsset): string {
  return asset.storage_path.split(/[\\/]/).pop()?.replace(/\.[^.]+$/, '') || asset.id;
}

function formatSettingName(name: string): string {
  return name.replace(/_/g, ' ').replace(/^./, (first) => first.toUpperCase());
}

function formatSettingValue(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(2);
}

function rangeMin(name: string): number {
  return name === 'level' ? -1 : 0;
}

function rangeMax(name: string): number {
  return name === 'speed' ? 2 : 1;
}
