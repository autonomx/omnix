import { Button, Group, Progress, Text, Title } from '@mantine/core';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useMemo } from 'react';
import { useForm } from 'react-hook-form';
import { omnixApiClient, type ProviderFacadePayload } from '../../api/client';
import type { OmnixModuleDefinition } from '../../app/modules';
import { OmnixAssetCard, OmnixStatusPill, WorkspacePanel } from '../../design/primitives';
import { FeatureSubmitFeedback, FeatureValidationMessage } from '../shared/FeatureSubmitFeedback';

interface ImageGenerationFormValues {
  providerId: string;
  prompt: string;
  width: string;
  height: string;
}

export function ImageGenerationWorkspace({ module }: { module: OmnixModuleDefinition }) {
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
  } = useForm<ImageGenerationFormValues>({
    defaultValues: { providerId: '', prompt: '', width: '768', height: '768' },
  });
  const imageProviders = useMemo(() => imageCapableProviders(providersQuery.data), [providersQuery.data]);
  const imageJobs = jobsQuery.data?.jobs.filter((job) => job.module === 'image-generation' || job.module === 'image') ?? [];
  const imageAssets = assetsQuery.data?.assets.filter((asset) => asset.type === 'image') ?? [];
  const createJobMutation = useMutation({
    mutationFn: (values: ImageGenerationFormValues) =>
      omnixApiClient.createJob({
        module: 'image-generation',
        type: 'image.generate',
        resource_class: 'gpu:image',
        priority: 0,
        input_payload: {
          prompt: values.prompt,
          provider_id: values.providerId || null,
          width: Number.parseInt(values.width, 10) || 768,
          height: Number.parseInt(values.height, 10) || 768,
        },
        stages: [
          { id: 'generate-image', label: 'Generate image', resource_class: 'gpu:image', status: 'queued' },
          { id: 'store-asset', label: 'Store image asset', resource_class: 'cpu', status: 'queued' },
        ],
      }),
    onSuccess: async (_job, values) => {
      reset({ providerId: values.providerId, prompt: '', width: values.width, height: values.height });
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
              <Title order={4}>Image request</Title>
              <Text size="sm">Shared image job queue</Text>
            </div>
            <OmnixStatusPill>{submitStatus}</OmnixStatusPill>
          </Group>

          <form className="feature-form" onSubmit={handleSubmit((values) => createJobMutation.mutate(values))}>
            <label>
              Provider
              <select {...register('providerId')}>
                <option value="">Default image provider</option>
                {imageProviders.map((provider) => (
                  <option key={provider.id} value={provider.id}>
                    {provider.label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Width
              <input type="number" min="128" step="64" {...register('width')} />
            </label>
            <label>
              Height
              <input type="number" min="128" step="64" {...register('height')} />
            </label>
            <label className="feature-form-wide">
              Prompt
              <textarea rows={5} aria-invalid={Boolean(errors.prompt)} {...register('prompt', { required: true })} />
            </label>
            <Button className="feature-form-action" type="submit" disabled={createJobMutation.isPending} loading={createJobMutation.isPending}>
              {createJobMutation.isPending ? 'Queueing image…' : 'Queue image'}
            </Button>
          </form>

          <FeatureValidationMessage show={Boolean(errors.prompt)} message="Enter a prompt before queueing image generation." />
          <FeatureSubmitFeedback
            error={createJobMutation.error}
            errorPrefix="Image request"
            isError={createJobMutation.isError}
            isPending={createJobMutation.isPending}
            jobId={createJobMutation.data?.id}
            pendingMessage="Queueing image job…"
            successPrefix="Image job queued"
          />
        </section>

        <section className="feature-panel">
          <Title order={4}>Image jobs</Title>
          {imageJobs.length ? (
            <div className="feature-list">
              {imageJobs.map((job) => (
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
              No image jobs queued.
            </div>
          )}
        </section>

        <section className="feature-panel feature-panel-wide">
          <Title order={4}>Image assets</Title>
          {imageAssets.length ? (
            <div className="platform-grid">
              {imageAssets.map((asset) => (
                <OmnixAssetCard key={asset.id} title={`${asset.type} / ${asset.module}`} metadata={asset.storage_path} />
              ))}
            </div>
          ) : (
            <div className="platform-empty" role="status">
              No image assets indexed.
            </div>
          )}
        </section>
      </div>
    </WorkspacePanel>
  );
}

function imageCapableProviders(payload: ProviderFacadePayload | undefined) {
  return payload?.providers.filter((provider) => provider.capabilities.includes('image')) ?? [];
}

function progressPercent(progress: { current: number; total: number } | undefined): number {
  if (!progress || progress.total <= 0) {
    return 0;
  }

  return Math.min(100, Math.round((progress.current / progress.total) * 100));
}
