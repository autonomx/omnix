import { Button, Group, Progress, Text, Title } from '@mantine/core';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { omnixApiClient } from '../../api/client';
import type { OmnixModuleDefinition } from '../../app/modules';
import { OmnixAssetCard, OmnixStatusPill, WorkspacePanel } from '../../design/primitives';
import { FeatureSubmitFeedback, FeatureValidationMessage } from '../shared/FeatureSubmitFeedback';

interface RpgFormValues {
  sessionId: string;
  command: string;
}

export function RpgWorkspace({ module }: { module: OmnixModuleDefinition }) {
  const queryClient = useQueryClient();
  const inventoryQuery = useQuery({
    queryKey: ['feature', 'rpg', 'replay-inventory'],
    queryFn: () => omnixApiClient.getReplayPersistenceInventory(),
  });
  const jobsQuery = useQuery({
    queryKey: ['platform', 'jobs'],
    queryFn: () => omnixApiClient.listJobs(),
  });
  const assetsQuery = useQuery({
    queryKey: ['platform', 'assets'],
    queryFn: () => omnixApiClient.listAssets(),
  });
  const reportsQuery = useQuery({
    queryKey: ['platform', 'reports'],
    queryFn: () => omnixApiClient.listReports(),
  });
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<RpgFormValues>({
    defaultValues: { sessionId: '', command: '' },
  });
  const sessions = inventoryQuery.data?.sessions ?? [];
  const rpgJobs = jobsQuery.data?.jobs.filter((job) => job.module === 'rpg') ?? [];
  const rpgAssets =
    assetsQuery.data?.assets.filter((asset) => asset.type === 'rpg_checkpoint' || asset.module === 'rpg') ?? [];
  const rpgReports = reportsQuery.data?.reports?.filter((report) => report.kind.includes('rpg') || report.id.includes('rpg')) ?? [];
  const createJobMutation = useMutation({
    mutationFn: (values: RpgFormValues) =>
      omnixApiClient.createJob({
        module: 'rpg',
        type: 'rpg.turn',
        resource_class: 'gpu:llm',
        priority: 0,
        input_ref: values.sessionId ? { session_id: values.sessionId } : null,
        input_payload: {
          command: values.command,
          determinism_policy: 'replay_preserving',
        },
        stages: [
          { id: 'load-session', label: 'Load session', resource_class: 'cpu', status: 'queued' },
          { id: 'apply-turn', label: 'Apply deterministic turn', resource_class: 'cpu', status: 'queued' },
          { id: 'narrate', label: 'Generate narration', resource_class: 'gpu:llm', status: 'queued' },
          { id: 'checkpoint', label: 'Write checkpoint', resource_class: 'cpu', status: 'queued' },
        ],
      }),
    onSuccess: async (_job, values) => {
      reset({ sessionId: values.sessionId, command: '' });
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
              <Title order={4}>Turn request</Title>
              <Text size="sm">Replay-preserving RPG handoff</Text>
            </div>
            <OmnixStatusPill>{submitStatus}</OmnixStatusPill>
          </Group>

          <form className="feature-form" onSubmit={handleSubmit((values) => createJobMutation.mutate(values))}>
            <label className="feature-form-wide">
              Session
              <select {...register('sessionId')}>
                <option value="">New or current session</option>
                {sessions.map((session, index) => {
                  const sessionId = safeSessionId(session, index);
                  return (
                    <option key={sessionId} value={sessionId}>
                      {sessionId}
                    </option>
                  );
                })}
              </select>
            </label>
            <label className="feature-form-wide">
              Command
              <textarea rows={5} aria-invalid={Boolean(errors.command)} {...register('command', { required: true })} />
            </label>
            <Button className="feature-form-action" type="submit" disabled={createJobMutation.isPending} loading={createJobMutation.isPending}>
              {createJobMutation.isPending ? 'Queueing RPG turn…' : 'Queue RPG turn'}
            </Button>
          </form>

          <FeatureValidationMessage show={Boolean(errors.command)} message="Enter a command before queueing an RPG turn." />
          <FeatureSubmitFeedback
            error={createJobMutation.error}
            errorPrefix="RPG turn request"
            isError={createJobMutation.isError}
            isPending={createJobMutation.isPending}
            jobId={createJobMutation.data?.id}
            pendingMessage="Queueing RPG turn job…"
            successPrefix="RPG turn job queued"
          />
        </section>

        <section className="feature-panel">
          <Title order={4}>RPG jobs</Title>
          {rpgJobs.length ? (
            <div className="feature-list">
              {rpgJobs.map((job) => (
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
              No RPG jobs queued.
            </div>
          )}
        </section>

        <section className="feature-panel">
          <Title order={4}>Sessions</Title>
          {sessions.length ? (
            <div className="feature-list">
              {sessions.map((session, index) => (
                <article className="feature-mini-card" key={safeSessionId(session, index)}>
                  <strong>{safeSessionId(session, index)}</strong>
                  <Text size="sm">{stringifySessionSummary(session)}</Text>
                </article>
              ))}
            </div>
          ) : (
            <div className="platform-empty" role="status">
              No RPG sessions found.
            </div>
          )}
        </section>

        <section className="feature-panel">
          <Title order={4}>Autoplay reports</Title>
          {rpgReports.length ? (
            <div className="feature-list">
              {rpgReports.map((report) => (
                <article className="feature-mini-card" key={report.id}>
                  <strong>{report.id}</strong>
                  <Text size="sm">{report.path}</Text>
                </article>
              ))}
            </div>
          ) : (
            <div className="platform-empty" role="status">
              No RPG reports found.
            </div>
          )}
        </section>

        <section className="feature-panel feature-panel-wide">
          <Title order={4}>RPG assets</Title>
          {rpgAssets.length ? (
            <div className="platform-grid">
              {rpgAssets.map((asset) => (
                <OmnixAssetCard key={asset.id} title={`${asset.type} / ${asset.module}`} metadata={asset.storage_path} />
              ))}
            </div>
          ) : (
            <div className="platform-empty" role="status">
              No RPG assets indexed.
            </div>
          )}
        </section>
      </div>
    </WorkspacePanel>
  );
}

function safeSessionId(session: Record<string, unknown>, index: number): string {
  const candidate = session.session_id ?? session.id ?? session.name ?? `session:${index + 1}`;
  return String(candidate);
}

function stringifySessionSummary(session: Record<string, unknown>): string {
  const fields = ['updated_at', 'created_at', 'path', 'status']
    .map((key) => session[key])
    .filter((value) => value !== undefined && value !== null && value !== '');
  return fields.length ? fields.map(String).join(' / ') : 'replay inventory entry';
}

function progressPercent(progress: { current: number; total: number } | undefined): number {
  if (!progress || progress.total <= 0) {
    return 0;
  }

  return Math.min(100, Math.round((progress.current / progress.total) * 100));
}
