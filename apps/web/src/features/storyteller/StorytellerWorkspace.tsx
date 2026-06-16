import { Button, Group, Progress, Text, Title } from '@mantine/core';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useMemo } from 'react';
import { useForm } from 'react-hook-form';
import { omnixApiClient, type ProviderFacadePayload } from '../../api/client';
import type { OmnixModuleDefinition } from '../../app/modules';
import { OmnixAssetCard, OmnixStatusPill, WorkspacePanel } from '../../design/primitives';
import { FeatureSubmitFeedback, FeatureValidationMessage } from '../shared/FeatureSubmitFeedback';

interface StorytellerFormValues {
  providerId: string;
  title: string;
  premise: string;
}

export function StorytellerWorkspace({ module }: { module: OmnixModuleDefinition }) {
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
  } = useForm<StorytellerFormValues>({
    defaultValues: { providerId: '', title: '', premise: '' },
  });
  const storyProviders = useMemo(() => llmCapableProviders(providersQuery.data), [providersQuery.data]);
  const storyJobs = jobsQuery.data?.jobs.filter((job) => job.module === 'storyteller') ?? [];
  const storyAssets = assetsQuery.data?.assets.filter((asset) => asset.type === 'story' || asset.type === 'export') ?? [];
  const createJobMutation = useMutation({
    mutationFn: (values: StorytellerFormValues) =>
      omnixApiClient.createJob({
        module: 'storyteller',
        type: 'story.generate',
        resource_class: 'gpu:llm',
        priority: 0,
        input_payload: {
          title: values.title || null,
          premise: values.premise,
          provider_id: values.providerId || null,
          prompt_template_id: 'storyteller.draft.v1',
        },
        stages: [
          { id: 'outline', label: 'Build outline', resource_class: 'gpu:llm', status: 'queued' },
          { id: 'draft', label: 'Draft story', resource_class: 'gpu:llm', status: 'queued' },
          { id: 'store-story', label: 'Store story asset', resource_class: 'cpu', status: 'queued' },
        ],
      }),
    onSuccess: async (_job, values) => {
      reset({ providerId: values.providerId, title: '', premise: '' });
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
              <Title order={4}>Story request</Title>
              <Text size="sm">Shared story job queue</Text>
            </div>
            <OmnixStatusPill>{submitStatus}</OmnixStatusPill>
          </Group>

          <form className="feature-form" onSubmit={handleSubmit((values) => createJobMutation.mutate(values))}>
            <label>
              Provider
              <select {...register('providerId')}>
                <option value="">Default LLM provider</option>
                {storyProviders.map((provider) => (
                  <option key={provider.id} value={provider.id}>
                    {provider.label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Title
              <input {...register('title')} placeholder="Untitled story" />
            </label>
            <label className="feature-form-wide">
              Premise
              <textarea rows={6} aria-invalid={Boolean(errors.premise)} {...register('premise', { required: true })} />
            </label>
            <Button className="feature-form-action" type="submit" disabled={createJobMutation.isPending} loading={createJobMutation.isPending}>
              {createJobMutation.isPending ? 'Queueing story…' : 'Queue story'}
            </Button>
          </form>

          <FeatureValidationMessage show={Boolean(errors.premise)} message="Enter a premise before queueing a story." />
          <FeatureSubmitFeedback
            error={createJobMutation.error}
            errorPrefix="Story request"
            isError={createJobMutation.isError}
            isPending={createJobMutation.isPending}
            jobId={createJobMutation.data?.id}
            pendingMessage="Queueing story job…"
            successPrefix="Story job queued"
          />
        </section>

        <section className="feature-panel">
          <Title order={4}>Story jobs</Title>
          {storyJobs.length ? (
            <div className="feature-list">
              {storyJobs.map((job) => (
                <article className="feature-mini-card" key={job.id}>
                  <Group justify="space-between">
                    <strong>{job.type}</strong>
                    <OmnixStatusPill>{job.status}</OmnixStatusPill>
                  </Group>
                  <Progress value={progressPercent(job.progress)} aria-label={`${job.type} progress`} />
                  <Text size="sm">{job.resource_class}</Text>
                  {jobOutputText(job) ? <Text size="sm">{jobOutputText(job)}</Text> : null}
                </article>
              ))}
            </div>
          ) : (
            <div className="platform-empty" role="status">
              No story jobs queued.
            </div>
          )}
        </section>

        <section className="feature-panel feature-panel-wide">
          <Title order={4}>Story assets</Title>
          {storyAssets.length ? (
            <div className="platform-grid">
              {storyAssets.map((asset) => (
                <OmnixAssetCard key={asset.id} title={`${asset.type} / ${asset.module}`} metadata={asset.storage_path} />
              ))}
            </div>
          ) : (
            <div className="platform-empty" role="status">
              No story assets indexed.
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

function progressPercent(progress: { current: number; total: number } | undefined): number {
  if (!progress || progress.total <= 0) {
    return 0;
  }

  return Math.min(100, Math.round((progress.current / progress.total) * 100));
}

function jobOutputText(job: { output_refs?: Array<{ content?: unknown }>; logs?: Array<{ content?: unknown }> }): string | null {
  const content = job.output_refs?.find((ref) => typeof ref.content === 'string')?.content ?? job.logs?.find((log) => typeof log.content === 'string')?.content;
  if (typeof content !== 'string') {
    return null;
  }
  return content.length > 260 ? `${content.slice(0, 260)}…` : content;
}
