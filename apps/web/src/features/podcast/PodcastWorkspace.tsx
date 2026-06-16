import { Button, Group, Progress, Text, Title } from '@mantine/core';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useMemo } from 'react';
import { useForm } from 'react-hook-form';
import { omnixApiClient, type ProviderFacadePayload } from '../../api/client';
import type { OmnixModuleDefinition } from '../../app/modules';
import { OmnixAssetCard, OmnixAudioControls, OmnixStatusPill, WorkspacePanel } from '../../design/primitives';
import { FeatureSubmitFeedback, FeatureValidationMessage } from '../shared/FeatureSubmitFeedback';

interface PodcastFormValues {
  providerId: string;
  ttsProviderId: string;
  title: string;
  brief: string;
  speakers: string;
}

export function PodcastWorkspace({ module }: { module: OmnixModuleDefinition }) {
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
    formState: { errors },
  } = useForm<PodcastFormValues>({
    defaultValues: { providerId: '', ttsProviderId: '', title: '', brief: '', speakers: 'Host, Guest' },
  });
  const llmProviders = useMemo(() => llmCapableProviders(providersQuery.data), [providersQuery.data]);
  const ttsProviders = useMemo(() => ttsCapableProviders(providersQuery.data), [providersQuery.data]);
  const podcastJobs = jobsQuery.data?.jobs.filter((job) => job.module === 'podcast') ?? [];
  const podcastAssets =
    assetsQuery.data?.assets.filter((asset) => asset.type === 'podcast_script' || asset.type === 'audio' || asset.type === 'export') ?? [];
  const createJobMutation = useMutation({
    mutationFn: (values: PodcastFormValues) =>
      omnixApiClient.createJob({
        module: 'podcast',
        type: 'podcast.generate',
        resource_class: 'gpu:llm',
        priority: 0,
        input_payload: {
          title: values.title || null,
          brief: values.brief,
          speakers: values.speakers
            .split(',')
            .map((speaker) => speaker.trim())
            .filter(Boolean),
          provider_id: values.providerId || null,
          tts_provider_id: values.ttsProviderId || null,
          prompt_template_id: 'podcast.plan.v1',
        },
        stages: [
          { id: 'plan', label: 'Plan episode', resource_class: 'gpu:llm', status: 'queued' },
          { id: 'script', label: 'Draft script', resource_class: 'gpu:llm', status: 'queued' },
          { id: 'voices', label: 'Synthesize voices', resource_class: 'gpu:tts', status: 'queued' },
          { id: 'mix', label: 'Mix audio', resource_class: 'cpu', status: 'queued' },
          { id: 'export', label: 'Store podcast assets', resource_class: 'cpu', status: 'queued' },
        ],
      }),
    onSuccess: async (_job, values) => {
      reset({
        providerId: values.providerId,
        ttsProviderId: values.ttsProviderId,
        title: '',
        brief: '',
        speakers: values.speakers,
      });
      await queryClient.invalidateQueries({ queryKey: ['platform', 'jobs'] });
    },
  });
  const submitStatus = createJobMutation.isPending ? 'queueing' : createJobMutation.isError ? 'error' : createJobMutation.data?.status ?? 'ready';

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
              <Title order={4}>Episode request</Title>
              <Text size="sm">Shared podcast job queue</Text>
            </div>
            <OmnixStatusPill>{submitStatus}</OmnixStatusPill>
          </Group>

          <form className="feature-form" onSubmit={handleSubmit((values) => createJobMutation.mutate(values))}>
            <label>
              LLM provider
              <select {...register('providerId')}>
                <option value="">Default LLM provider</option>
                {llmProviders.map((provider) => (
                  <option key={provider.id} value={provider.id}>
                    {provider.label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              TTS provider
              <select {...register('ttsProviderId')}>
                <option value="">Default TTS provider</option>
                {ttsProviders.map((provider) => (
                  <option key={provider.id} value={provider.id}>
                    {provider.label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Title
              <input {...register('title')} placeholder="Untitled episode" />
            </label>
            <label>
              Speakers
              <input {...register('speakers')} />
            </label>
            <label className="feature-form-wide">
              Brief
              <textarea rows={5} aria-invalid={Boolean(errors.brief)} {...register('brief', { required: true })} />
            </label>
            <Button className="feature-form-action" type="submit" disabled={createJobMutation.isPending} loading={createJobMutation.isPending}>
              {createJobMutation.isPending ? 'Queueing episode…' : 'Queue episode'}
            </Button>
          </form>

          <FeatureValidationMessage show={Boolean(errors.brief)} message="Enter an episode brief before queueing a podcast." />
          <FeatureSubmitFeedback
            error={createJobMutation.error}
            errorPrefix="Podcast request"
            isError={createJobMutation.isError}
            isPending={createJobMutation.isPending}
            jobId={createJobMutation.data?.id}
            pendingMessage="Queueing podcast job…"
            successPrefix="Podcast job queued"
          />

          <OmnixAudioControls label="latest podcast mix" />
        </section>

        <section className="feature-panel">
          <Title order={4}>Podcast jobs</Title>
          {podcastJobs.length ? (
            <div className="feature-list">
              {podcastJobs.map((job) => (
                <article className="feature-mini-card" key={job.id}>
                  <Group justify="space-between">
                    <strong>{job.type}</strong>
                    <OmnixStatusPill>{job.status}</OmnixStatusPill>
                  </Group>
                  <Progress value={progressPercent(job.progress)} aria-label={`${job.type} progress`} />
                  <Text size="sm">{job.stages?.map((stage) => stage.label).join(' / ') || job.resource_class}</Text>
                </article>
              ))}
            </div>
          ) : (
            <div className="platform-empty" role="status">
              No podcast jobs queued.
            </div>
          )}
        </section>

        <section className="feature-panel feature-panel-wide">
          <Title order={4}>Podcast assets</Title>
          {podcastAssets.length ? (
            <div className="platform-grid">
              {podcastAssets.map((asset) => (
                <OmnixAssetCard key={asset.id} title={`${asset.type} / ${asset.module}`} metadata={asset.storage_path} />
              ))}
            </div>
          ) : (
            <div className="platform-empty" role="status">
              No podcast assets indexed.
            </div>
          )}
        </section>
      </div>
    </WorkspacePanel>
  );
}

function llmCapableProviders(payload: ProviderFacadePayload | undefined) {
  return payload?.providers.filter((provider) => provider.capabilities.includes('chat') || provider.capabilities.includes('completion')) ?? [];
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
