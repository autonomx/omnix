import { Button, Group, Progress, Switch, Text, Title } from '@mantine/core';
import { useMutation, useQuery, useQueryClient, type QueryKey, type UseQueryResult } from '@tanstack/react-query';
import { useEffect, useState, type ReactNode } from 'react';
import type {
  AssetListResponse,
  DiagnosticsPayload,
  JobListResponse,
  JobRecord,
  ProviderFacadePayload,
  ReportListResponse,
  SettingsPayload,
} from '../../api/client';
import { omnixApiClient } from '../../api/client';
import type { OmnixModuleDefinition, OmnixModuleId } from '../../app/modules';
import { OmnixAssetCard, OmnixDiagnosticsView, OmnixStatusPill, WorkspacePanel } from '../../design/primitives';
import { omnixEventClient, type OmnixEventConnectionStatus } from '../../events/eventClient';

const platformModuleIds = new Set<OmnixModuleId>([
  'providers',
  'models',
  'jobs',
  'assets',
  'reports',
  'settings',
  'diagnostics',
]);

const jobEventNames = ['job.created', 'job.updated', 'job.completed', 'job.failed', 'job.canceled'] as const;
const jobsEventQueryKeys: QueryKey[] = [['platform', 'jobs'], ['platform', 'diagnostics']];
const diagnosticsEventQueryKeys: QueryKey[] = [['platform', 'diagnostics'], ['platform', 'jobs']];
const artifactEventQueryKeys: QueryKey[] = [['platform', 'assets'], ['platform', 'reports']];
const providerModelEventQueryKeys: QueryKey[] = [
  ['platform', 'providers'],
  ['platform', 'models'],
  ['platform', 'jobs'],
  ['platform', 'diagnostics'],
];

export function isPlatformModule(moduleId: OmnixModuleId): boolean {
  return platformModuleIds.has(moduleId);
}

export function PlatformModuleWorkspace({ module }: { module: OmnixModuleDefinition }) {
  return (
    <WorkspacePanel>
      <div className="workspace-heading">
        <div>
          <p className="eyebrow">Platform module</p>
          <h3 id="module-title">{module.label}</h3>
        </div>
        <code>{module.route}</code>
      </div>

      <p className="workspace-summary">{module.summary}</p>

      {module.id === 'providers' ? <ProvidersView /> : null}
      {module.id === 'models' ? <ModelsView /> : null}
      {module.id === 'jobs' ? <JobsView /> : null}
      {module.id === 'assets' ? <AssetsView /> : null}
      {module.id === 'reports' ? <ReportsView /> : null}
      {module.id === 'settings' ? <SettingsView /> : null}
      {module.id === 'diagnostics' ? <DiagnosticsView /> : null}
    </WorkspacePanel>
  );
}

function ProvidersView() {
  const queryClient = useQueryClient();
  useJobEventRefresh(providerModelEventQueryKeys);
  const query = useQuery({
    queryKey: ['platform', 'providers'],
    queryFn: () => omnixApiClient.listProviders(),
  });
  const refreshMutation = useMutation({
    mutationFn: () => omnixApiClient.refreshProviders({ scope: 'providers', reason: 'web.providers.refresh', priority: 0 }),
    onSuccess: async () => {
      for (const queryKey of providerModelEventQueryKeys) {
        await queryClient.invalidateQueries({ queryKey });
      }
    },
  });

  return (
    <>
      <section className="platform-section">
        <Group justify="space-between" align="center">
          <Title order={4}>Registry refresh</Title>
          <Button size="xs" variant="light" disabled={refreshMutation.isPending} onClick={() => refreshMutation.mutate()}>
            Refresh
          </Button>
        </Group>
        <DetailList rows={[['Last request', refreshMutation.isError ? refreshMutation.error.message : refreshMutation.isSuccess ? 'queued' : 'idle']]} />
      </section>
      <QueryState query={query} empty={!query.data?.providers.length} emptyText="No providers returned by gateway.">
        {(data) => (
          <div className="platform-grid">
            {data.providers.map((provider) => (
              <section className="platform-section" key={provider.id}>
                <Group justify="space-between" align="start">
                  <div>
                    <Title order={4}>{provider.label}</Title>
                    <Text size="sm">{provider.source}</Text>
                  </div>
                  <OmnixStatusPill>{provider.status}</OmnixStatusPill>
                </Group>
                <DetailList
                  rows={[
                    ['Family', provider.family],
                    ['Capabilities', provider.capabilities.join(', ') || 'none'],
                    ['Latency', metadataValue(provider.metadata, 'latency_ms')],
                    ['Errors', metadataValue(provider.metadata, 'last_error')],
                  ]}
                />
              </section>
            ))}
          </div>
        )}
      </QueryState>
    </>
  );
}

function ModelsView() {
  const queryClient = useQueryClient();
  useJobEventRefresh(providerModelEventQueryKeys);
  const query = useQuery({
    queryKey: ['platform', 'models'],
    queryFn: () => omnixApiClient.listModels(),
  });
  const refreshMutation = useMutation({
    mutationFn: () => omnixApiClient.refreshModels({ scope: 'models', reason: 'web.models.refresh', priority: 0 }),
    onSuccess: async () => {
      for (const queryKey of providerModelEventQueryKeys) {
        await queryClient.invalidateQueries({ queryKey });
      }
    },
  });

  return (
    <>
      <section className="platform-section">
        <Group justify="space-between" align="center">
          <Title order={4}>Model refresh</Title>
          <Button size="xs" variant="light" disabled={refreshMutation.isPending} onClick={() => refreshMutation.mutate()}>
            Refresh
          </Button>
        </Group>
        <DetailList rows={[['Last request', refreshMutation.isError ? refreshMutation.error.message : refreshMutation.isSuccess ? 'queued' : 'idle']]} />
      </section>
      <QueryState query={query} empty={!query.data?.models.length} emptyText="No models returned by gateway.">
        {(data) => (
          <div className="platform-grid">
            {data.models.map((model) => (
              <section className="platform-section" key={model.id}>
                <Group justify="space-between" align="start">
                  <div>
                    <Title order={4}>{model.label}</Title>
                    <Text size="sm">{model.provider_id}</Text>
                  </div>
                  <OmnixStatusPill>{model.location}</OmnixStatusPill>
                </Group>
                <DetailList
                  rows={[
                    ['Capabilities', model.capabilities.join(', ') || 'none'],
                    ['VRAM hint', model.vram_hint_mb ? `${model.vram_hint_mb} MB` : 'unknown'],
                    ['Default for', metadataValue(model.metadata, 'default_for')],
                  ]}
                />
              </section>
            ))}
          </div>
        )}
      </QueryState>
    </>
  );
}

function JobsView() {
  const queryClient = useQueryClient();
  const eventStatus = useEventConnectionStatus();
  useJobEventRefresh(jobsEventQueryKeys);
  const query = useQuery({
    queryKey: ['platform', 'jobs'],
    queryFn: () => omnixApiClient.listJobs(),
  });
  const cancelMutation = useMutation({
    mutationFn: (jobId: string) => omnixApiClient.cancelJob(jobId, 'Canceled from Omnix web Jobs module'),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['platform', 'jobs'] }),
  });

  return (
    <>
      <section className="platform-section">
        <Title order={4}>Live updates</Title>
        <DetailList rows={eventStatusRows(eventStatus)} />
      </section>
      <QueryState query={query} empty={!query.data?.jobs.length} emptyText="No jobs in the shared queue.">
        {(data) => (
          <div className="platform-list">
            {data.jobs.map((job) => {
              const progressValue = progressPercent(job.progress);
              const canCancel = ['queued', 'leased', 'running', 'waiting', 'retrying'].includes(job.status);

              return (
                <section className="platform-section" key={job.id}>
                  <Group justify="space-between" align="start">
                    <div>
                      <Title order={4}>{job.type}</Title>
                      <Text size="sm">{job.module}</Text>
                    </div>
                    <Group gap="xs">
                      <OmnixStatusPill>{job.status}</OmnixStatusPill>
                      <Button
                        size="xs"
                        variant="light"
                        disabled={!canCancel || cancelMutation.isPending}
                        onClick={() => cancelMutation.mutate(job.id)}
                      >
                        Cancel
                      </Button>
                    </Group>
                  </Group>
                  <Progress value={progressValue} aria-label={`${job.type} progress`} />
                  <DetailList
                    rows={[
                      ['Resource lock', job.resource_class],
                      ['Progress', job.progress?.message ?? `${progressValue}%`],
                      ['Stages', job.stages?.map((stage) => `${stage.label}: ${stage.status}`).join(', ') || 'none'],
                      ['Logs', job.logs?.length ? `${job.logs.length}` : 'none'],
                    ]}
                  />
                </section>
              );
            })}
          </div>
        )}
      </QueryState>
    </>
  );
}

function AssetsView() {
  useJobEventRefresh(artifactEventQueryKeys);
  const query = useQuery({
    queryKey: ['platform', 'assets'],
    queryFn: () => omnixApiClient.listAssets(),
  });

  return (
    <QueryState query={query} empty={!query.data?.assets.length} emptyText="No assets indexed in the shared library.">
      {(data) => (
        <div className="platform-grid">
          {data.assets.map((asset) => (
            <OmnixAssetCard
              key={asset.id}
              title={`${asset.type} / ${asset.module}`}
              metadata={`${asset.mime_type} - ${asset.storage_path}`}
            />
          ))}
        </div>
      )}
    </QueryState>
  );
}

function ReportsView() {
  useJobEventRefresh(artifactEventQueryKeys);
  const query = useQuery({
    queryKey: ['platform', 'reports'],
    queryFn: () => omnixApiClient.listReports(),
  });

  return (
    <QueryState query={query} empty={!query.data?.reports?.length} emptyText="No generated reports found.">
      {(data) => (
        <div className="platform-grid">
          {(data.reports ?? []).map((report) => (
            <section className="platform-section" key={report.id}>
              <Group justify="space-between" align="start">
                <div>
                  <Title order={4}>{report.id}</Title>
                  <Text size="sm">{report.path}</Text>
                </div>
                <OmnixStatusPill>{report.kind}</OmnixStatusPill>
              </Group>
              <DetailList rows={[['Size', `${report.size_bytes} bytes`]]} />
            </section>
          ))}
        </div>
      )}
    </QueryState>
  );
}

function SettingsView() {
  const query = useQuery({
    queryKey: ['platform', 'settings'],
    queryFn: () => omnixApiClient.getSettings(),
  });

  return (
    <QueryState query={query} empty={!query.data} emptyText="Settings payload is unavailable.">
      {(data) => (
        <div className="platform-grid">
          <section className="platform-section">
            <Title order={4}>Provider defaults</Title>
            <DetailList
              rows={[
                ['LLM provider', data.provider],
                ['TTS provider', data.audio_provider_tts],
                ['STT provider', data.audio_provider_stt],
              ]}
            />
          </section>
          <section className="platform-section">
            <Title order={4}>Local services</Title>
            <div className="platform-switches">
              <Switch label="Image generation" checked={data.image_enabled} readOnly />
              <Switch label="RPG visuals" checked={data.rpg_visual_enabled} readOnly />
            </div>
            <DetailList rows={Object.entries(data.worker_urls ?? {}).map(([key, value]) => [key, value])} />
          </section>
        </div>
      )}
    </QueryState>
  );
}

function DiagnosticsView() {
  const eventStatus = useEventConnectionStatus();
  useJobEventRefresh(diagnosticsEventQueryKeys);
  const query = useQuery({
    queryKey: ['platform', 'diagnostics'],
    queryFn: () => omnixApiClient.getDiagnostics(),
  });

  return (
    <QueryState query={query} empty={!query.data} emptyText="Diagnostics payload is unavailable.">
      {(data) => {
        const workerRows =
          data.workers.workers?.map((worker) => ({
            label: worker.id,
            value: worker.ok ? worker.status : worker.error ?? worker.status,
          })) ?? [];

        return (
          <div className="platform-grid">
            <section className="platform-section">
              <Title order={4}>Gateway status</Title>
              <OmnixDiagnosticsView
                rows={[
                  { label: 'Gateway', value: data.status },
                  { label: 'Workers', value: data.workers.status },
                  { label: 'Event stream', value: eventStatusText(eventStatus) },
                  { label: 'Diagnostics payload', value: data.event_stream?.status ?? 'unknown' },
                  { label: 'Model residency', value: data.model_residency?.status ?? 'unknown' },
                  {
                    label: 'Co-residency',
                    value: data.model_residency?.policy?.allow_co_residency ? 'enabled' : 'conservative',
                  },
                  { label: 'Provider cache', value: data.provider_model_cache?.status ?? 'unknown' },
                ]}
              />
            </section>
            <section className="platform-section">
              <Title order={4}>Worker health</Title>
              {workerRows.length ? <OmnixDiagnosticsView rows={workerRows} /> : <EmptyState text="No workers configured." />}
            </section>
            <section className="platform-section platform-section-wide">
              <Title order={4}>Logs</Title>
              <div className="platform-log">
                {(data.logs ?? []).length ? data.logs?.map((log, index) => <code key={index}>{stringifyUnknown(log)}</code>) : <span>none</span>}
              </div>
            </section>
          </div>
        );
      }}
    </QueryState>
  );
}

function QueryState<T>({
  query,
  empty,
  emptyText,
  children,
}: {
  query: UseQueryResult<T, Error>;
  empty: boolean;
  emptyText: string;
  children: (data: T) => ReactNode;
}) {
  if (query.isLoading) {
    return <EmptyState text="Loading platform data." />;
  }

  if (query.isError) {
    return <EmptyState text={`Gateway request failed: ${query.error.message}`} />;
  }

  if (!query.data || empty) {
    return <EmptyState text={emptyText} />;
  }

  return <>{children(query.data)}</>;
}

function useEventConnectionStatus(): OmnixEventConnectionStatus {
  const [status, setStatus] = useState(() => omnixEventClient.getStatus());

  useEffect(() => omnixEventClient.subscribeStatus(setStatus), []);

  return status;
}

function useJobEventRefresh(queryKeys: QueryKey[]) {
  const queryClient = useQueryClient();

  useEffect(() => {
    const invalidate = () => {
      for (const queryKey of queryKeys) {
        queryClient.invalidateQueries({ queryKey });
      }
    };
    const unsubscribes = jobEventNames.map((eventName) => omnixEventClient.subscribe(eventName, invalidate));

    return () => {
      for (const unsubscribe of unsubscribes) {
        unsubscribe();
      }
    };
  }, [queryClient, queryKeys]);
}

function DetailList({ rows }: { rows: Array<[string, string]> }) {
  return (
    <dl className="platform-details">
      {rows.map(([label, value]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function EmptyState({ text }: { text: string }) {
  return (
    <div className="platform-empty" role="status">
      {text}
    </div>
  );
}

function eventStatusRows(status: OmnixEventConnectionStatus): Array<[string, string]> {
  return [
    ['Event stream', eventStatusText(status)],
    ['Retry attempt', `${status.reconnectAttempt}`],
    ['Next retry', status.nextReconnectDelayMs ? `${status.nextReconnectDelayMs} ms` : 'none'],
  ];
}

function eventStatusText(status: OmnixEventConnectionStatus): string {
  return status.lastError ? `${status.state} (${status.lastError})` : status.state;
}

function progressPercent(progress: JobRecord['progress']): number {
  if (!progress || progress.total <= 0) {
    return 0;
  }

  return Math.min(100, Math.round((progress.current / progress.total) * 100));
}

function metadataValue(metadata: Record<string, unknown> | undefined, key: string): string {
  const value = metadata?.[key];

  if (value === undefined || value === null || value === '') {
    return 'unknown';
  }

  return typeof value === 'string' ? value : stringifyUnknown(value);
}

function stringifyUnknown(value: unknown): string {
  if (typeof value === 'string') {
    return value;
  }

  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}
