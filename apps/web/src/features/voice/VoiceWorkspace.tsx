import { Button, Group, Progress, Text, Title } from '@mantine/core';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useMemo } from 'react';
import { useForm } from 'react-hook-form';
import { omnixApiClient, type ProviderFacadePayload } from '../../api/client';
import type { OmnixModuleDefinition } from '../../app/modules';
import { OmnixAssetCard, OmnixAudioControls, OmnixStatusPill, WorkspacePanel } from '../../design/primitives';

interface VoiceFormValues {
  text: string;
  speaker: string;
  voiceId: string;
  providerId: string;
}

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
  const { register, handleSubmit, reset } = useForm<VoiceFormValues>({
    defaultValues: { text: '', speaker: '', voiceId: '', providerId: '' },
  });
  const ttsProviders = useMemo(() => ttsCapableProviders(providersQuery.data), [providersQuery.data]);
  const voiceJobs = jobsQuery.data?.jobs.filter((job) => job.module === 'voice') ?? [];
  const audioAssets = assetsQuery.data?.assets.filter((asset) => asset.type === 'audio' || asset.type === 'voice_profile') ?? [];
  const createJobMutation = useMutation({
    mutationFn: (values: VoiceFormValues) =>
      omnixApiClient.createJob({
        module: 'voice',
        type: 'tts.synthesize',
        resource_class: 'gpu:tts',
        priority: 0,
        input_payload: {
          text: values.text,
          speaker: values.speaker || null,
          voice_id: values.voiceId || null,
          provider_id: values.providerId || null,
        },
        stages: [
          { id: 'synthesize', label: 'Synthesize speech', resource_class: 'gpu:tts', status: 'queued' },
          { id: 'store-audio', label: 'Store audio asset', resource_class: 'cpu', status: 'queued' },
        ],
      }),
    onSuccess: async (_job, values) => {
      reset({ text: '', speaker: values.speaker, voiceId: values.voiceId, providerId: values.providerId });
      await queryClient.invalidateQueries({ queryKey: ['platform', 'jobs'] });
    },
  });

  return (
    <WorkspacePanel>
      <div className="workspace-heading">
        <div>
          <p className="eyebrow">Feature module</p>
          <h2 id="module-title">{module.label}</h2>
        </div>
        <code>{module.route}</code>
      </div>

      <p className="workspace-summary">{module.summary}</p>

      <div className="feature-layout">
        <section className="feature-panel">
          <Group justify="space-between" align="start">
            <div>
              <Title order={4}>Synthesis</Title>
              <Text size="sm">Shared voice job queue</Text>
            </div>
            <OmnixStatusPill>{createJobMutation.data?.status ?? 'ready'}</OmnixStatusPill>
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
              Voice ID
              <input {...register('voiceId')} placeholder="optional" />
            </label>
            <label className="feature-form-wide">
              Text
              <textarea rows={5} {...register('text', { required: true })} />
            </label>
            <Button className="feature-form-action" type="submit" disabled={createJobMutation.isPending}>
              Queue synthesis
            </Button>
          </form>

          {createJobMutation.data ? (
            <div className="feature-job-link" role="status">
              TTS job queued: {createJobMutation.data.id}
            </div>
          ) : null}

          <OmnixAudioControls label="latest voice preview" />
        </section>

        <section className="feature-panel">
          <Title order={4}>Voice jobs</Title>
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
        </section>

        <section className="feature-panel feature-panel-wide">
          <Title order={4}>Audio assets</Title>
          {audioAssets.length ? (
            <div className="platform-grid">
              {audioAssets.map((asset) => (
                <OmnixAssetCard key={asset.id} title={`${asset.type} / ${asset.module}`} metadata={asset.storage_path} />
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

function ttsCapableProviders(payload: ProviderFacadePayload | undefined) {
  return payload?.providers.filter((provider) => provider.capabilities.includes('tts')) ?? [];
}

function progressPercent(progress: { current: number; total: number } | undefined): number {
  if (!progress || progress.total <= 0) {
    return 0;
  }

  return Math.min(100, Math.round((progress.current / progress.total) * 100));
}
