import { Button, Group, Progress, Text, Title } from '@mantine/core';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useMemo } from 'react';
import { useForm } from 'react-hook-form';
import { omnixApiClient, type ProviderFacadePayload } from '../../api/client';
import type { OmnixModuleDefinition } from '../../app/modules';
import { OmnixAssetCard, OmnixAudioControls, OmnixStatusPill, WorkspacePanel } from '../../design/primitives';

interface VoiceCloningFormValues {
  providerId: string;
  sampleAssetId: string;
  profileName: string;
  referenceText: string;
}

export function VoiceCloningWorkspace({ module }: { module: OmnixModuleDefinition }) {
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
  const { register, handleSubmit, reset } = useForm<VoiceCloningFormValues>({
    defaultValues: { providerId: '', sampleAssetId: '', profileName: '', referenceText: '' },
  });
  const providers = useMemo(() => voiceCloneCapableProviders(providersQuery.data), [providersQuery.data]);
  const sampleAssets = assetsQuery.data?.assets.filter((asset) => asset.type === 'voice_sample' || asset.type === 'audio') ?? [];
  const profileAssets = assetsQuery.data?.assets.filter((asset) => asset.type === 'voice_profile') ?? [];
  const voiceCloneJobs = jobsQuery.data?.jobs.filter((job) => job.module === 'voice-cloning') ?? [];
  const createJobMutation = useMutation({
    mutationFn: (values: VoiceCloningFormValues) =>
      omnixApiClient.createJob({
        module: 'voice-cloning',
        type: 'voice-cloning.train',
        resource_class: 'gpu:tts',
        priority: 0,
        input_ref: values.sampleAssetId ? { sample_asset_id: values.sampleAssetId } : null,
        input_payload: {
          provider_id: values.providerId || null,
          profile_name: values.profileName,
          reference_text: values.referenceText || null,
        },
        stages: [
          { id: 'ingest-sample', label: 'Ingest sample', resource_class: 'cpu', status: 'queued' },
          { id: 'build-profile', label: 'Build voice profile', resource_class: 'gpu:tts', status: 'queued' },
          { id: 'preview', label: 'Generate preview', resource_class: 'gpu:tts', status: 'queued' },
          { id: 'store-profile', label: 'Store voice profile asset', resource_class: 'cpu', status: 'queued' },
        ],
      }),
    onSuccess: async (_job, values) => {
      reset({ providerId: values.providerId, sampleAssetId: values.sampleAssetId, profileName: '', referenceText: '' });
      await queryClient.invalidateQueries({ queryKey: ['platform', 'jobs'] });
    },
  });

  return (
    <WorkspacePanel>
      <div className="workspace-heading">
        <div>
          <p className="eyebrow">Feature module</p>
          <h3 id="module-title">{module.label}</h3>
        </div>
        <code>{module.route}</code>
      </div>

      <p className="workspace-summary">{module.summary}</p>

      <div className="feature-layout">
        <section className="feature-panel">
          <Group justify="space-between" align="start">
            <div>
              <Title order={4}>Voice profile</Title>
              <Text size="sm">Shared voice-cloning job queue</Text>
            </div>
            <OmnixStatusPill>{createJobMutation.data?.status ?? 'ready'}</OmnixStatusPill>
          </Group>

          <form className="feature-form" onSubmit={handleSubmit((values) => createJobMutation.mutate(values))}>
            <label>
              Provider
              <select {...register('providerId')}>
                <option value="">Default voice provider</option>
                {providers.map((provider) => (
                  <option key={provider.id} value={provider.id}>
                    {provider.label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Sample asset
              <select {...register('sampleAssetId')}>
                <option value="">No sample selected</option>
                {sampleAssets.map((asset) => (
                  <option key={asset.id} value={asset.id}>
                    {asset.storage_path}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Profile name
              <input {...register('profileName', { required: true })} placeholder="Narrator profile" />
            </label>
            <label className="feature-form-wide">
              Reference text
              <textarea rows={4} {...register('referenceText')} />
            </label>
            <Button className="feature-form-action" type="submit" disabled={createJobMutation.isPending}>
              Queue voice profile
            </Button>
          </form>

          {createJobMutation.data ? (
            <div className="feature-job-link" role="status">
              Voice profile job queued: {createJobMutation.data.id}
            </div>
          ) : null}

          <OmnixAudioControls label="voice profile preview" />
        </section>

        <section className="feature-panel">
          <Title order={4}>Voice profile jobs</Title>
          {voiceCloneJobs.length ? (
            <div className="feature-list">
              {voiceCloneJobs.map((job) => (
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
              No voice profile jobs queued.
            </div>
          )}
        </section>

        <section className="feature-panel feature-panel-wide">
          <Title order={4}>Voice profiles</Title>
          {profileAssets.length ? (
            <div className="platform-grid">
              {profileAssets.map((asset) => (
                <OmnixAssetCard key={asset.id} title={`${asset.type} / ${asset.module}`} metadata={asset.storage_path} />
              ))}
            </div>
          ) : (
            <div className="platform-empty" role="status">
              No voice profiles indexed.
            </div>
          )}
        </section>
      </div>
    </WorkspacePanel>
  );
}

function voiceCloneCapableProviders(payload: ProviderFacadePayload | undefined) {
  return payload?.providers.filter((provider) => provider.capabilities.includes('voice_cloning') || provider.capabilities.includes('tts')) ?? [];
}

function progressPercent(progress: { current: number; total: number } | undefined): number {
  if (!progress || progress.total <= 0) {
    return 0;
  }

  return Math.min(100, Math.round((progress.current / progress.total) * 100));
}
