import { Text, Title } from '@mantine/core';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';
import { omnixApiClient, type AssetListResponse, type JobListResponse, type JobRecord } from '../../api/client';
import type { OmnixModuleDefinition } from '../../app/modules';
import { OmnixStatusPill, WorkspacePanel } from '../../design/primitives';
import { imageGenerationDefaults } from '../settings/moduleDefaults';
import { loadSettingsProfile } from '../settings/settingsApi';
import { FeatureSubmitFeedback } from '../shared/FeatureSubmitFeedback';
import { ImageAssetGallery } from './ImageAssetGallery';
import './ImageGenerationWorkspace.css';
import './ImageGenerationWorkspaceInteractions.css';
import { ImageJobList } from './ImageJobList';
import { ImageLatestResult } from './ImageLatestResult';
import {
  ImageModelControl,
  imageModelGenerationBlockReason,
  type ImageModelStatusPayload,
} from './ImageModelControl';
import { ImageReadinessPanel } from './ImageReadinessPanel';
import { ImageRequestForm } from './ImageRequestForm';
import {
  readyImageProviders,
  resolveImageReadiness,
  type WorkerHealthPayload,
} from './imageReadinessModel';
import { buildImageGenerateInput, type ImageRequestFormValues } from './imageRequestModel';
import {
  IMAGE_ASSETS_QUERY_KEY,
  IMAGE_JOB_EVENT_TYPES,
  IMAGE_JOBS_QUERY_KEY,
  hasActiveImageJobs,
  isImageJobEventPayload,
  parseJobEvent,
  selectLatestImageAsset,
} from './imageWorkspaceModel';

const IMAGE_MODEL_QUERY_KEY = ['image-generation', 'model-status'] as const;

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'Image model action failed.';
}

export function ImageGenerationWorkspaceImpl({ module }: { module: OmnixModuleDefinition }) {
  const queryClient = useQueryClient();
  const [selectedAssetId, setSelectedAssetId] = useState<string | null>(null);
  const providersQuery = useQuery({ queryKey: ['platform', 'providers'], queryFn: () => omnixApiClient.listProviders() });
  const workersQuery = useQuery({
    queryKey: ['image-generation', 'worker-health'],
    queryFn: () => omnixApiClient.get<WorkerHealthPayload>('/api/workers/health'),
    refetchInterval: 30_000,
  });
  const modelStatusQuery = useQuery({
    queryKey: IMAGE_MODEL_QUERY_KEY,
    queryFn: () => omnixApiClient.get<ImageModelStatusPayload>('/api/image-generation/model/status'),
    refetchInterval: (query) => {
      const state = query.state.data?.state;
      return state === 'loading' || state === 'unloading' ? 1_000 : 10_000;
    },
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

  const imageProviders = useMemo(() => readyImageProviders(providersQuery.data), [providersQuery.data]);
  const readiness = useMemo(() => resolveImageReadiness({
    providers: providersQuery.data,
    workers: workersQuery.data,
    loading: providersQuery.isLoading || settingsQuery.isLoading,
    providerError: providersQuery.isError,
    workerError: workersQuery.isError,
  }), [providersQuery.data, providersQuery.isError, providersQuery.isLoading, settingsQuery.isLoading, workersQuery.data, workersQuery.isError]);
  const imageJobs = jobsQuery.data?.jobs ?? [];
  const imageAssets = assetsQuery.data?.assets ?? [];

  const loadModelMutation = useMutation({
    mutationFn: () => omnixApiClient.post<{ provider: string }, ImageModelStatusPayload>(
      '/api/image-generation/model/load',
      { provider: 'flux_klein' },
    ),
    onSuccess: async () => Promise.all([
      queryClient.invalidateQueries({ queryKey: IMAGE_MODEL_QUERY_KEY }),
      queryClient.invalidateQueries({ queryKey: ['image-generation', 'worker-health'] }),
    ]),
  });
  const unloadModelMutation = useMutation({
    mutationFn: () => omnixApiClient.post<{ provider: string }, ImageModelStatusPayload>(
      '/api/image-generation/model/unload',
      { provider: 'flux_klein' },
    ),
    onSuccess: async () => Promise.all([
      queryClient.invalidateQueries({ queryKey: IMAGE_MODEL_QUERY_KEY }),
      queryClient.invalidateQueries({ queryKey: ['image-generation', 'worker-health'] }),
    ]),
  });
  const modelAction = loadModelMutation.isPending ? 'load' : unloadModelMutation.isPending ? 'unload' : null;
  const modelBlockReason = imageModelGenerationBlockReason(
    modelStatusQuery.data,
    modelStatusQuery.isLoading,
    modelStatusQuery.isError,
  );
  const generationDisabledReason = !readiness.canGenerate ? readiness.message : modelBlockReason;

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
  const submitStatus = createJobMutation.isPending
    ? 'queueing'
    : createJobMutation.isError
      ? 'error'
      : modelStatusQuery.data?.loaded
        ? createJobMutation.data?.status ?? readiness.status
        : 'model unloaded';

  const refreshReadiness = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['platform', 'providers'] }),
      queryClient.invalidateQueries({ queryKey: ['image-generation', 'worker-health'] }),
      queryClient.invalidateQueries({ queryKey: IMAGE_MODEL_QUERY_KEY }),
      queryClient.invalidateQueries({ queryKey: ['settings', 'profile'] }),
    ]);
  };

  const openAssetInGallery = (assetId: string) => {
    setSelectedAssetId(assetId);
    document.getElementById('image-assets')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  const modelActionError = loadModelMutation.isError
    ? errorMessage(loadModelMutation.error)
    : unloadModelMutation.isError
      ? errorMessage(unloadModelMutation.error)
      : modelStatusQuery.isError
        ? errorMessage(modelStatusQuery.error)
        : undefined;
  const systemStatus = modelStatusQuery.data?.loaded ? 'ready' : modelStatusQuery.isError ? 'blocked' : 'degraded';
  const systemTitle = modelStatusQuery.data?.loaded
    ? `${modelStatusQuery.data.model} loaded`
    : `${modelStatusQuery.data?.model || 'FLUX.2 [klein] 4B'} unloaded`;
  const systemMessage = modelStatusQuery.data?.loaded
    ? 'Image generation is ready.'
    : 'The service is running without model weights in memory.';

  return (
    <WorkspacePanel className="image-workspace">
      <h2 id="module-title" className="visually-hidden">{module.label}</h2>

      <div className="image-workspace-status-row">
        <section className="image-flow-banner" aria-label="Image generation flow">
          <span className="image-flow-icon" aria-hidden="true">⌾</span>
          <p><strong>Flow:</strong> Load the model <b>→</b> submit a request <b>→</b> the result appears in Latest Result and Image Assets.</p>
        </section>
        <section className={`image-system-card ${systemStatus}`} aria-live="polite">
          <span className="image-system-dot" aria-hidden="true" />
          <div><strong>{systemTitle}</strong><small>{systemMessage}</small></div>
          <span className="image-system-wave">{modelStatusQuery.data?.state || 'checking'}</span>
        </section>
      </div>

      <div className="image-workspace-grid">
        <section className="image-surface image-request-card" aria-labelledby="image-request-title">
          <header className="image-section-header">
            <div className="image-section-heading">
              <span className="image-section-icon" aria-hidden="true">▧</span>
              <div>
                <Title id="image-request-title" order={3} aria-label="Image request">Image Request</Title>
                <Text size="sm">Load FLUX when needed, then configure and submit an image request.</Text>
              </div>
            </div>
            <OmnixStatusPill>{submitStatus}</OmnixStatusPill>
          </header>
          <ImageReadinessPanel
            readiness={readiness}
            refreshing={providersQuery.isFetching || workersQuery.isFetching || settingsQuery.isFetching || modelStatusQuery.isFetching}
            onRefresh={() => void refreshReadiness()}
          />
          <ImageModelControl
            status={modelStatusQuery.data}
            statusLoading={modelStatusQuery.isLoading || modelStatusQuery.isFetching}
            action={modelAction}
            error={modelActionError}
            onLoad={() => loadModelMutation.mutate()}
            onUnload={() => unloadModelMutation.mutate()}
            onRefresh={() => void modelStatusQuery.refetch()}
          />
          <ImageRequestForm
            defaults={moduleDefaults}
            providers={imageProviders}
            pending={createJobMutation.isPending}
            disabled={Boolean(generationDisabledReason) || Boolean(modelAction)}
            disabledReason={generationDisabledReason}
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

        <aside className="image-workspace-rail">
          <section className="image-surface image-jobs-card" aria-labelledby="image-jobs-title">
            <header className="image-section-header image-section-header-compact">
              <div className="image-section-heading">
                <span className="image-section-icon" aria-hidden="true">☷</span>
                <div><Title id="image-jobs-title" order={3}>Image Jobs</Title><Text size="sm">Monitor and manage queued generations.</Text></div>
              </div>
            </header>
            <ImageJobList
              jobs={imageJobs}
              cancelingJobId={cancelJobMutation.isPending ? cancelJobMutation.variables : undefined}
              retryingJobId={retryJobMutation.isPending ? retryJobMutation.variables : undefined}
              onCancel={(jobId) => cancelJobMutation.mutate(jobId)}
              onRetry={(jobId) => retryJobMutation.mutate(jobId)}
              onSelectAsset={setSelectedAssetId}
            />
            {cancelJobMutation.isError ? <Text c="red" size="sm" role="alert">Image job cancel failed.</Text> : null}
            {retryJobMutation.isError ? <Text c="red" size="sm" role="alert">Image job retry failed.</Text> : null}
          </section>

          <ImageLatestResult asset={latestAsset} onOpenInAssets={openAssetInGallery} />
        </aside>

        <section id="image-assets" className="image-surface image-assets-card" aria-labelledby="image-assets-title">
          <header className="image-section-header image-assets-heading">
            <div className="image-section-heading">
              <span className="image-section-icon" aria-hidden="true">▣</span>
              <div><Title id="image-assets-title" order={3}>Image Assets</Title><Text size="sm">Browse and manage generated images and assets.</Text></div>
            </div>
          </header>
          <ImageAssetGallery assets={imageAssets} selectedAssetId={selectedAssetId} onSelect={setSelectedAssetId} />
        </section>
      </div>
    </WorkspacePanel>
  );
}
