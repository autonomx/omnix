import { Button, Group, Text, Title } from '@mantine/core';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo } from 'react';
import { useForm } from 'react-hook-form';
import {
  omnixApiClient,
  type AssetListResponse,
  type JobListResponse,
  type JobRecord,
  type ProviderFacadePayload,
} from '../../api/client';
import type { OmnixModuleDefinition } from '../../app/modules';
import { OmnixAssetCard, OmnixStatusPill, WorkspacePanel } from '../../design/primitives';
import { imageGenerationDefaults } from '../settings/moduleDefaults';
import { loadSettingsProfile } from '../settings/settingsApi';
import { FeatureSubmitFeedback, FeatureValidationMessage } from '../shared/FeatureSubmitFeedback';
import { ImageJobList } from './ImageJobList';

const IMAGE_JOBS_QUERY_KEY = ['image-generation', 'jobs'] as const;
const IMAGE_ASSETS_QUERY_KEY = ['image-generation', 'assets'] as const;
const IMAGE_JOB_EVENT_TYPES = ['job.created', 'job.updated', 'job.completed', 'job.failed', 'job.canceled'] as const;
const ACTIVE_IMAGE_JOB_STATUSES = new Set(['queued', 'waiting', 'retrying', 'leased', 'running', 'cancel_requested']);

type ImageAsset = AssetListResponse['assets'][number];

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
    queryKey: IMAGE_JOBS_QUERY_KEY,
    queryFn: () => omnixApiClient.get<JobListResponse>('/api/image-generation/jobs'),
    refetchInterval: (query) => (hasActiveImageJobs(query.state.data) ? 1_500 : false),
  });
  const assetsQuery = useQuery({
    queryKey: IMAGE_ASSETS_QUERY_KEY,
    queryFn: () => omnixApiClient.get<AssetListResponse>('/api/image-generation/assets'),
  });
  const settingsQuery = useQuery({
    queryKey: ['settings', 'profile'],
    queryFn: loadSettingsProfile,
  });
  const moduleDefaults = useMemo(() => imageGenerationDefaults(settingsQuery.data?.profile), [settingsQuery.data?.profile]);
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isDirty },
  } = useForm<ImageGenerationFormValues>({
    defaultValues: { providerId: '', prompt: '', width: '768', height: '768' },
  });

  useEffect(() => {
    if (!settingsQuery.data || isDirty) return;
    reset({ providerId: moduleDefaults.providerId, prompt: '', width: String(moduleDefaults.width), height: String(moduleDefaults.height) });
  }, [isDirty, moduleDefaults, reset, settingsQuery.data]);

  useEffect(() => {
    if (typeof EventSource === 'undefined') return;
    const source = new EventSource('/events');
    const handleEvent = (event: Event) => {
      if (!(event instanceof MessageEvent)) return;
      const payload = parseJobEvent(event.data);
      if (!isImageJobEventPayload(payload)) return;
      void queryClient.invalidateQueries({ queryKey: IMAGE_JOBS_QUERY_KEY });
      if (event.type === 'job.completed') void queryClient.invalidateQueries({ queryKey: IMAGE_ASSETS_QUERY_KEY });
    };
    IMAGE_JOB_EVENT_TYPES.forEach((eventType) => source.addEventListener(eventType, handleEvent));
    return () => {
      IMAGE_JOB_EVENT_TYPES.forEach((eventType) => source.removeEventListener(eventType, handleEvent));
      source.close();
    };
  }, [queryClient]);

  const imageProviders = useMemo(() => imageCapableProviders(providersQuery.data), [providersQuery.data]);
  const imageJobs = jobsQuery.data?.jobs ?? [];
  const imageAssets = assetsQuery.data?.assets ?? [];
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
          width: Number.parseInt(values.width, 10) || moduleDefaults.width,
          height: Number.parseInt(values.height, 10) || moduleDefaults.height,
          unload_after_generation: moduleDefaults.unloadAfterGeneration,
        },
        stages: [
          { id: 'generate-image', label: 'Generate image', resource_class: 'gpu:image', status: 'queued' },
          { id: 'store-asset', label: 'Store image asset', resource_class: 'cpu', status: 'queued' },
        ],
      }),
    onSuccess: async (_job, values) => {
      reset({ providerId: values.providerId, prompt: '', width: values.width, height: values.height });
      await queryClient.invalidateQueries({ queryKey: IMAGE_JOBS_QUERY_KEY });
    },
  });
  const cancelJobMutation = useMutation({
    mutationFn: (jobId: string) => omnixApiClient.cancelJob(jobId, 'Canceled from Image Generation workspace'),
    onSuccess: async () => queryClient.invalidateQueries({ queryKey: IMAGE_JOBS_QUERY_KEY }),
  });
  const retryJobMutation = useMutation({
    mutationFn: (jobId: string) =>
      omnixApiClient.post<Record<string, never>, JobRecord>(
        `/api/image-generation/jobs/${encodeURIComponent(jobId)}/retry`,
        {},
      ),
    onSuccess: async () => queryClient.invalidateQueries({ queryKey: IMAGE_JOBS_QUERY_KEY }),
  });
  const latestAsset = useMemo(
    () => selectLatestImageAsset(imageAssets, imageJobs, null, createJobMutation.data?.id),
    [createJobMutation.data?.id, imageAssets, imageJobs],
  );
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
                {imageProviders.map((provider) => <option key={provider.id} value={provider.id}>{provider.label}</option>)}
              </select>
            </label>
            <label>Width<input type="number" min="128" step="64" {...register('width')} /></label>
            <label>Height<input type="number" min="128" step="64" {...register('height')} /></label>
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
          <ImageJobList
            jobs={imageJobs}
            cancelingJobId={cancelJobMutation.isPending ? cancelJobMutation.variables : undefined}
            retryingJobId={retryJobMutation.isPending ? retryJobMutation.variables : undefined}
            onCancel={(jobId) => cancelJobMutation.mutate(jobId)}
            onRetry={(jobId) => retryJobMutation.mutate(jobId)}
          />
          {cancelJobMutation.isError ? <Text c="red" size="sm" role="alert">Image job cancel failed.</Text> : null}
          {retryJobMutation.isError ? <Text c="red" size="sm" role="alert">Image job retry failed.</Text> : null}
        </section>

        <section className="feature-panel feature-panel-wide" aria-labelledby="latest-image-result-title">
          <Group justify="space-between" align="start">
            <div>
              <Title id="latest-image-result-title" order={4}>Latest result</Title>
              <Text size="sm">Your most recently generated image appears here first.</Text>
            </div>
            {latestAsset ? <OmnixStatusPill>completed</OmnixStatusPill> : null}
          </Group>
          {latestAsset ? (
            <div style={{ display: 'grid', gap: '1rem', gridTemplateColumns: 'minmax(220px, 420px) 1fr', marginTop: '1rem' }}>
              <img
                src={imageAssetUrl(latestAsset.id)}
                alt={imageAssetTitle(latestAsset)}
                style={{ aspectRatio: '1 / 1', borderRadius: '0.75rem', objectFit: 'cover', width: '100%' }}
              />
              <div>
                <Title order={5}>{imageAssetTitle(latestAsset)}</Title>
                <Text size="sm" mt="xs">{imageAssetMetadata(latestAsset)}</Text>
                <Text size="sm" mt="xs">Generated {formatCreatedAt(latestAsset.created_at)}</Text>
                <Group mt="md">
                  <Button component="a" href={imageAssetUrl(latestAsset.id)} target="_blank" rel="noreferrer" variant="light">Open image</Button>
                  <Button component="a" href={imageAssetUrl(latestAsset.id, true)} download variant="default">Download</Button>
                </Group>
              </div>
            </div>
          ) : <div className="platform-empty" role="status" style={{ marginTop: '1rem' }}>Generate an image to see the latest result here.</div>}
        </section>

        <section className="feature-panel feature-panel-wide">
          <Title order={4}>Image assets</Title>
          {imageAssets.length ? (
            <div className="platform-grid">
              {imageAssets.map((asset) => <OmnixAssetCard key={asset.id} title={`${asset.type} / ${asset.module}`} metadata={asset.storage_path} />)}
            </div>
          ) : <div className="platform-empty" role="status">No image assets indexed.</div>}
        </section>
      </div>
    </WorkspacePanel>
  );
}

function imageCapableProviders(payload: ProviderFacadePayload | undefined) {
  return payload?.providers.filter((provider) => provider.family === 'image' && provider.capabilities.includes('image')) ?? [];
}

export function isImageJobEventPayload(value: unknown): boolean {
  if (!value || typeof value !== 'object') return false;
  const payload = (value as { payload?: unknown }).payload;
  if (!payload || typeof payload !== 'object') return false;
  const job = payload as { module?: unknown; type?: unknown };
  return job.type === 'image.generate' || job.module === 'image' || job.module === 'image-generation';
}

export function hasActiveImageJobs(payload: JobListResponse | undefined): boolean {
  return payload?.jobs.some((job) => ACTIVE_IMAGE_JOB_STATUSES.has(job.status)) ?? false;
}

export function selectLatestImageAsset(
  assets: ImageAsset[],
  jobs: JobRecord[],
  selectedAssetId: string | null,
  submittedJobId?: string,
): ImageAsset | undefined {
  const byId = new Map(assets.map((asset) => [asset.id, asset]));
  if (selectedAssetId && byId.has(selectedAssetId)) return byId.get(selectedAssetId);
  if (submittedJobId) {
    const submittedAsset = assets.find((asset) => asset.source_job_id === submittedJobId);
    if (submittedAsset) return submittedAsset;
  }
  for (const job of jobs) {
    for (const ref of job.output_refs ?? []) {
      const assetId = typeof ref.asset_id === 'string' ? ref.asset_id : '';
      if (assetId && byId.has(assetId)) return byId.get(assetId);
    }
  }
  return assets[0];
}

export function imageAssetUrl(assetId: string, download = false): string {
  return `/api/assets/${encodeURIComponent(assetId)}/file${download ? '?download=true' : ''}`;
}

function imageAssetTitle(asset: ImageAsset): string {
  return metadataString(asset, 'title') || metadataString(asset, 'prompt') || 'Generated image';
}

function imageAssetMetadata(asset: ImageAsset): string {
  const width = metadataNumber(asset, 'width');
  const height = metadataNumber(asset, 'height');
  const provider = metadataString(asset, 'provider_key') || metadataString(asset, 'provider_id');
  return [width && height ? `${width} × ${height}` : '', provider].filter(Boolean).join(' · ') || asset.mime_type;
}

function metadataString(asset: ImageAsset, key: string): string {
  const value = asset.metadata?.[key];
  return typeof value === 'string' ? value : '';
}

function metadataNumber(asset: ImageAsset, key: string): number | undefined {
  const value = asset.metadata?.[key];
  return typeof value === 'number' ? value : undefined;
}

function formatCreatedAt(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function parseJobEvent(data: unknown): unknown {
  if (typeof data !== 'string') return undefined;
  try { return JSON.parse(data); } catch { return undefined; }
}
