import { Group, Text, Title } from '@mantine/core';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';
import { omnixApiClient, type AssetListResponse, type JobListResponse, type JobRecord } from '../../api/client';
import type { OmnixModuleDefinition } from '../../app/modules';
import { OmnixStatusPill, WorkspacePanel } from '../../design/primitives';
import { imageGenerationDefaults } from '../settings/moduleDefaults';
import { loadSettingsProfile } from '../settings/settingsApi';
import { FeatureSubmitFeedback } from '../shared/FeatureSubmitFeedback';
import { ImageAssetGallery } from './ImageAssetGallery';
import { ImageJobList } from './ImageJobList';
import { ImageLatestResult } from './ImageLatestResult';
import { ImageRequestForm } from './ImageRequestForm';
import { buildImageGenerateInput, type ImageRequestFormValues } from './imageRequestModel';
import {
  IMAGE_ASSETS_QUERY_KEY,
  IMAGE_JOB_EVENT_TYPES,
  IMAGE_JOBS_QUERY_KEY,
  hasActiveImageJobs,
  imageCapableProviders,
  isImageJobEventPayload,
  parseJobEvent,
  selectLatestImageAsset,
} from './imageWorkspaceModel';

export function ImageGenerationWorkspaceImpl({ module }: { module: OmnixModuleDefinition }) {
  const queryClient = useQueryClient();
  const [selectedAssetId, setSelectedAssetId] = useState<string | null>(null);
  const providersQuery = useQuery({ queryKey: ['platform', 'providers'], queryFn: () => omnixApiClient.listProviders() });
  const jobsQuery = useQuery({
    queryKey: IMAGE_JOBS_QUERY_KEY,
    queryFn: () => omnixApiClient.get<JobListResponse>('/api/image-generation/jobs'),
    refetchInterval: (query) => (hasActiveImageJobs(query.state.data) ? 1_500 : false),
  });
  const assetsQuery = useQuery({
    queryKey: IMAGE_ASSETS_QUERY_KEY,
    queryFn: () => omnixApiClient.get<AssetListResponse>('/api/image-generation/assets'),
  });
  const settingsQuery = useQuery({ queryKey: ['settings', 'profile'], queryFn: loadSettingsProfile });
  const moduleDefaults = useMemo(() => imageGenerationDefaults(settingsQuery.data?.profile), [settingsQuery.data?.profile]);

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
    mutationFn: (values: ImageRequestFormValues) => omnixApiClient.createJob({
      module: 'image-generation',
      type: 'image.generate',
      resource_class: 'gpu:image',
      priority: 0,
      input_payload: buildImageGenerateInput(values, moduleDefaults),
      stages: [
        { id: 'generate-image', label: 'Generate image', resource_class: 'gpu:image', status: 'queued' },
        { id: 'store-asset', label: 'Store image asset', resource_class: 'cpu', status: 'queued' },
      ],
    }),
    onSuccess: async () => queryClient.invalidateQueries({ queryKey: IMAGE_JOBS_QUERY_KEY }),
  });
  const cancelJobMutation = useMutation({
    mutationFn: (jobId: string) => omnixApiClient.cancelJob(jobId, 'Canceled from Image Generation workspace'),
    onSuccess: async () => queryClient.invalidateQueries({ queryKey: IMAGE_JOBS_QUERY_KEY }),
  });
  const retryJobMutation = useMutation({
    mutationFn: (jobId: string) => omnixApiClient.post<Record<string, never>, JobRecord>(
      `/api/image-generation/jobs/${encodeURIComponent(jobId)}/retry`,
      {},
    ),
    onSuccess: async () => queryClient.invalidateQueries({ queryKey: IMAGE_JOBS_QUERY_KEY }),
  });
  const latestAsset = useMemo(
    () => selectLatestImageAsset(imageAssets, imageJobs, selectedAssetId, createJobMutation.data?.id),
    [createJobMutation.data?.id, imageAssets, imageJobs, selectedAssetId],
  );
  const submitStatus = createJobMutation.isPending ? 'queueing' : createJobMutation.isError ? 'error' : createJobMutation.data?.status ?? 'ready';

  return (
    <WorkspacePanel>
      <div className="workspace-heading">
        <div><p className="eyebrow">Feature module</p><h2 id="module-title">{module.label}</h2></div>
        <code>{module.route}</code>
      </div>
      <p className="workspace-summary">{module.summary}</p>
      <div className="feature-layout">
        <section className="feature-panel">
          <Group justify="space-between" align="start">
            <div><Title order={4}>Image request</Title><Text size="sm">Provider-aware controls with presets and optional tuning.</Text></div>
            <OmnixStatusPill>{submitStatus}</OmnixStatusPill>
          </Group>
          <ImageRequestForm
            defaults={moduleDefaults}
            providers={imageProviders}
            pending={createJobMutation.isPending}
            resetToken={createJobMutation.data?.id}
            onSubmit={(values) => createJobMutation.mutate(values)}
          />
          <FeatureSubmitFeedback
            error={createJobMutation.error}
            errorPrefix="Image request"
            isError={createJobMutation.isError}
            isPending={createJobMutation.isPending}
            jobId={createJobMutation.data?.id}
            pendingMessage="Queueing image job..."
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

        <ImageLatestResult asset={latestAsset} />

        <section className="feature-panel feature-panel-wide">
          <Title order={4}>Image assets</Title>
          <ImageAssetGallery assets={imageAssets} selectedAssetId={selectedAssetId} onSelect={setSelectedAssetId} />
        </section>
      </div>
    </WorkspacePanel>
  );
}
