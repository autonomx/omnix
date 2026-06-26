import { Button, Group, Progress, Text, Title } from '@mantine/core';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useMemo } from 'react';
import { useForm } from 'react-hook-form';
import { omnixApiClient, type AssetListResponse, type ProviderFacadePayload } from '../../api/client';
import type { OmnixModuleDefinition } from '../../app/modules';
import { OmnixAssetCard, OmnixAudioControls, OmnixStatusPill, WorkspacePanel } from '../../design/primitives';
import { FeatureSubmitFeedback, FeatureValidationMessage } from '../shared/FeatureSubmitFeedback';
import { DEFAULT_OUTPUT_SETTINGS } from './outputDefaults';
import { firstResultAsset } from './resultList';
import { parseScriptSpeakers } from './scriptLines';

interface VoiceFormValues {
  text: string;
  speaker: string;
  voiceId: string;
  providerId: string;
}

type VoiceAsset = AssetListResponse['assets'][number];

export function VoiceWorkspace({ module }: { module: OmnixModuleDefinition }) {
  const queryClient = useQueryClient();
  const providersQuery = useQuery({
    queryKey: ['platform', 'providers'],
    queryFn: () => omnixApiClient.listProviders(),
  });
  const jobsQuery = useQuery({
    queryKey: ['platform', 'jobs'],
    queryFn: () => omnixApiClient.listJobs(),
  });
  const assetsQuery = useQuery({
    queryKey: ['platform', 'assets'],
    queryFn: () => omnixApiClient.listAssets(),
  });
  const {
    register,
    handleSubmit,
    reset,
    watch,
    formState: { errors },
  } = useForm<VoiceFormValues>({
    defaultValues: { text: '', speaker: '', voiceId: '', providerId: '' },
  });
  const textDraft = watch('text');
  const parsedSpeakers = useMemo(() => parseScriptSpeakers(textDraft), [textDraft]);
  const ttsProviders = useMemo(() => ttsCapableProviders(providersQuery.data), [providersQuery.data]);
  const voiceJobs = jobsQuery.data?.jobs.filter((job) => job.module === 'voice' || job.module === 'voice-cloning') ?? [];
  const audioAssets = assetsQuery.data?.assets.filter((asset) => asset.type === 'audio' || asset.type === 'voice_profile') ?? [];
  const profileAssets = audioAssets.filter((asset) => asset.type === 'voice_profile');
  const generatedAudioAssets = audioAssets.filter((asset) => asset.type === 'audio');
  const latestResultAsset = firstResultAsset(generatedAudioAssets);
  const createJobMutation = useMutation({
    mutationFn: (values: VoiceFormValues) =>
      omnixApiClient.createJob({
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
  const submitStatus = createJobMutation.isPending ? 'queueing' : createJobMutation.isError ? 'error' : createJobMutation.data?.status ?? 'ready';

  return (
    <WorkspacePanel>
      <div className="workspace-heading">
        <div>
          <p className="eyebrow">Feature module</p>
          <h2 id="module-title">Voice Studio</h2>
        </div>
        <code>{module.route}</code>
      </div>

      <p className="workspace-summary">Text-to-speech generation, local voice profiles, previews, playback, and provider diagnostics.</p>

      <div className="feature-layout">
        <section className="feature-panel">
          <Group justify="space-between" align="start">
            <div>
              <Title order={4}>Synthesis Composer</Title>
              <Text size="sm">Shared voice job queue</Text>
            </div>
            <OmnixStatusPill>{submitStatus}</OmnixStatusPill>
          </Group>

          <form className="feature-form" onSubmit={handleSubmit((values) => createJobMutation.mutate(values))}>
            <label>
              Provider
              <select {...register('providerId')}>
                <option value="">Default TTS provider</option>
                {ttsProviders.map((provider) => (
                  <option key={provider.id} value={provider.id}>
                    {provider.label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Speaker
              <input {...register('speaker')} placeholder="Narrator" />
            </label>
            <label>
              Voice profile
              <select {...register('voiceId')}>
                <option value="">Manual / default voice</option>
                {profileAssets.map((asset) => (
                  <option key={asset.id} value={asset.storage_path}>
                    {voiceAssetName(asset)}
                  </option>
                ))}
              </select>
            </label>
            <label className="feature-form-wide">
              Text
              <textarea rows={6} aria-invalid={Boolean(errors.text)} {...register('text', { required: true })} />
            </label>
            <Button className="feature-form-action" type="submit" disabled={createJobMutation.isPending} loading={createJobMutation.isPending}>
              {createJobMutation.isPending ? 'Queueing synthesis…' : 'Queue synthesis'}
            </Button>
          </form>

          <FeatureValidationMessage show={Boolean(errors.text)} message="Enter text before queueing speech synthesis." />
          <FeatureSubmitFeedback
            error={createJobMutation.error}
            errorPrefix="TTS request"
            isError={createJobMutation.isError}
            isPending={createJobMutation.isPending}
            jobId={createJobMutation.data?.id}
            pendingMessage="Queueing TTS job…"
            successPrefix="TTS job queued"
          />

          <OmnixAudioControls label="latest voice preview" />
        </section>

        <section className="feature-panel">
          <Group justify="space-between" align="start">
            <div>
              <Title order={4}>Output Controls</Title>
              <Text size="sm">Visible defaults sent with synthesis jobs.</Text>
            </div>
            <OmnixStatusPill>ready</OmnixStatusPill>
          </Group>
          <div className="feature-list">
            {Object.entries(DEFAULT_OUTPUT_SETTINGS).map(([name, value]) => (
              <label className="feature-mini-card" key={name}>
                <Group justify="space-between">
                  <strong>{formatSettingName(name)}</strong>
                  <OmnixStatusPill>{formatSettingValue(value)}</OmnixStatusPill>
                </Group>
                <input aria-label={`Output ${name}`} type="range" min={rangeMin(name)} max={rangeMax(name)} step="0.01" value={value} readOnly />
              </label>
            ))}
          </div>
        </section>

        <section className="feature-panel">
          <Group justify="space-between" align="start">
            <div>
              <Title order={4}>Detected Characters</Title>
              <Text size="sm">Lines written as name: text are grouped automatically.</Text>
            </div>
            <OmnixStatusPill>{parsedSpeakers.length} detected</OmnixStatusPill>
          </Group>
          {parsedSpeakers.length ? (
            <div className="feature-list">
              {parsedSpeakers.map((speaker) => (
                <article className="feature-mini-card" key={speaker.name}>
                  <Group justify="space-between">
                    <strong>{speaker.name}</strong>
                    <OmnixStatusPill>{speaker.count} lines</OmnixStatusPill>
                  </Group>
                </article>
              ))}
            </div>
          ) : (
            <div className="platform-empty" role="status">
              Type speaker-tagged lines to detect characters.
            </div>
          )}
        </section>

        <section className="feature-panel">
          <Group justify="space-between" align="start">
            <div>
              <Title order={4}>Voice Library</Title>
              <Text size="sm">Local profiles available for synthesis.</Text>
            </div>
            <OmnixStatusPill>{profileAssets.length} voices</OmnixStatusPill>
          </Group>
          {profileAssets.length ? (
            <div className="feature-list">
              {profileAssets.map((asset) => (
                <article className="feature-mini-card" key={asset.id}>
                  <Group justify="space-between">
                    <strong>{voiceAssetName(asset)}</strong>
                    <OmnixStatusPill>ready</OmnixStatusPill>
                  </Group>
                  <Text size="sm">{asset.storage_path}</Text>
                  <Group gap="xs">
                    <Button size="xs" variant="light">Preview</Button>
                    <Button size="xs" variant="light">Use</Button>
                    <Button size="xs" variant="subtle">Edit</Button>
                  </Group>
                </article>
              ))}
            </div>
          ) : (
            <div className="platform-empty" role="status">
              No voice profiles indexed.
            </div>
          )}
        </section>

        <section className="feature-panel">
          <Title order={4}>Jobs & Playback Queue</Title>
          {voiceJobs.length ? (
            <div className="feature-list">
              {voiceJobs.map((job) => (
                <article className="feature-mini-card" key={job.id}>
                  <Group justify="space-between">
                    <strong>{job.type}</strong>
                    <OmnixStatusPill>{job.status}</OmnixStatusPill>
                  </Group>
                  <Progress value={progressPercent(job.progress)} aria-label={`${job.type} progress`} />
                  <Text size="sm">{job.resource_class}</Text>
                </article>
              ))}
            </div>
          ) : (
            <div className="platform-empty" role="status">
              No voice jobs queued.
            </div>
          )}
          {latestResultAsset ? (
            <article className="feature-mini-card">
              <Group justify="space-between">
                <strong>Latest output</strong>
                <OmnixStatusPill>{voiceAssetName(latestResultAsset)}</OmnixStatusPill>
              </Group>
              <OmnixAudioControls label={voiceAssetName(latestResultAsset)} />
              <Group gap="xs">
                <Button size="xs" variant="light">Export</Button>
                <Button size="xs" variant="subtle">Keep</Button>
              </Group>
            </article>
          ) : null}
        </section>

        <section className="feature-panel feature-panel-wide">
          <Title order={4}>Audio assets</Title>
          {audioAssets.length ? (
            <div className="platform-grid">
              {audioAssets.map((asset) => (
                asset.type === 'audio' ? <AudioOutputCard key={asset.id} asset={asset} /> : <OmnixAssetCard key={asset.id} title={`${asset.type} / ${asset.module}`} metadata={asset.storage_path} />
              ))}
            </div>
          ) : (
            <div className="platform-empty" role="status">
              No audio assets indexed.
            </div>
          )}
        </section>
      </div>
    </WorkspacePanel>
  );
}

function AudioOutputCard({ asset }: { asset: VoiceAsset }) {
  return (
    <article className="feature-mini-card">
      <Group justify="space-between">
        <Title order={4}>{`${asset.type} / ${asset.module}`}</Title>
        <OmnixStatusPill>{asset.mime_type}</OmnixStatusPill>
      </Group>
      <Text size="sm">{asset.storage_path}</Text>
      <OmnixAudioControls label={voiceAssetName(asset)} />
      <Group gap="xs">
        <Button size="xs" variant="light">Export</Button>
        <Button size="xs" variant="subtle">Keep</Button>
      </Group>
    </article>
  );
}

function ttsCapableProviders(payload: ProviderFacadePayload | undefined) {
  return payload?.providers.filter((provider) => provider.capabilities.includes('tts')) ?? [];
}

function progressPercent(progress: { current: number; total: number } | undefined): number {
  if (!progress || progress.total <= 0) {
    return 0;
  }
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
