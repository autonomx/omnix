import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { omnixApiClient } from '../../api/client';
import type { OmnixModuleDefinition } from '../../app/modules';
import { WorkspacePanel } from '../../design/primitives';
import { FeatureSubmitFeedback, FeatureValidationMessage } from '../shared/FeatureSubmitFeedback';
import { RpgActionComposer } from './RpgActionComposer';
import { RpgCombatSurface } from './RpgCombatSurface';
import { RpgLoadoutTabs } from './RpgLoadoutTabs';
import { RpgNarrativeTabs } from './RpgNarrativeTabs';
import { RpgPlayerRail } from './RpgPlayerRail';
import { RpgStoryScene } from './RpgStoryScene';
import { RpgWorkspaceHeader } from './RpgWorkspaceHeader';
import { RpgWorldRail } from './RpgWorldRail';
import { createRpgCombatSurfaceState } from './rpgCombatState';
import { createRpgWorkspaceState } from './rpgUiState';
import './RpgWorkspace.css';

interface RpgFormValues {
  sessionId: string;
  command: string;
}

const ACTIVE_JOB_STATUSES = new Set(['queued', 'leased', 'running', 'waiting', 'retrying', 'cancel_requested']);

export function RpgWorkspace({ module }: { module: OmnixModuleDefinition }) {
  const queryClient = useQueryClient();
  const [isPlayerRailCollapsed, setIsPlayerRailCollapsed] = useState(false);
  const [isWorldRailCollapsed, setIsWorldRailCollapsed] = useState(false);
  const inventoryQuery = useQuery({
    queryKey: ['feature', 'rpg', 'replay-inventory'],
    queryFn: () => omnixApiClient.getReplayPersistenceInventory(),
  });
  const jobsQuery = useQuery({
    queryKey: ['platform', 'jobs'],
    queryFn: () => omnixApiClient.listJobs(),
    refetchInterval: 3000,
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
    setValue,
    watch,
    formState: { errors },
  } = useForm<RpgFormValues>({
    defaultValues: { sessionId: '', command: '' },
  });
  const selectedSessionId = watch('sessionId');
  const {
    heroSummary,
    heroStats,
    equippedGear,
    partyMembers,
    activeQuests,
    quickActions,
    recentEvents,
    journalEntries,
    journalDetail,
    inventoryItems,
    hotbarAbilities,
    worldStateRows,
    npcRelationships,
    encounter,
    sessionSummaries,
    selectedSessionSummary,
    checkpointSummary,
    rpgJobs,
    rpgAssets,
    rpgReports,
    jobCards,
  } = createRpgWorkspaceState({
    inventory: inventoryQuery.data,
    jobs: jobsQuery.data,
    assets: assetsQuery.data,
    reports: reportsQuery.data,
    selectedSessionId,
  });
  const combatSurface = createRpgCombatSurfaceState({ encounter, heroSummary, partyMembers });
  const selectedLiveSessionId = selectedSessionSummary.source === 'live' ? selectedSessionSummary.id : null;
  const activeAutoplayJob = rpgJobs.find((job) => job.type === 'rpg.autoplay' && ACTIVE_JOB_STATUSES.has(job.status));
  const dashboardClassName = [
    'rpg-dashboard-grid',
    isPlayerRailCollapsed ? 'rpg-dashboard-grid-left-collapsed' : '',
    isWorldRailCollapsed ? 'rpg-dashboard-grid-right-collapsed' : '',
  ]
    .filter(Boolean)
    .join(' ');
  const invalidateRpgWorkspaceQueries = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['feature', 'rpg', 'replay-inventory'] }),
      queryClient.invalidateQueries({ queryKey: ['platform', 'jobs'] }),
      queryClient.invalidateQueries({ queryKey: ['platform', 'assets'] }),
      queryClient.invalidateQueries({ queryKey: ['platform', 'reports'] }),
    ]);
  };
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
      await invalidateRpgWorkspaceQueries();
    },
  });
  const createCheckpointMutation = useMutation({
    mutationFn: () =>
      omnixApiClient.createReplayCheckpoint({
        source: 'rpg-workspace',
        version: 'rpg-ui-control-v1',
        metadata: {
          module: 'rpg',
          session_id: selectedLiveSessionId,
          session_title: selectedSessionSummary.title,
          reason: 'manual-ui-checkpoint',
        },
        payload: {
          selected_session_id: selectedLiveSessionId,
          title: selectedSessionSummary.title,
          location: selectedSessionSummary.location,
          turn_label: selectedSessionSummary.turnLabel,
          checkpoint_label: selectedSessionSummary.checkpointLabel,
        },
      }),
    onSuccess: async () => {
      await invalidateRpgWorkspaceQueries();
    },
  });
  const autoplayMutation = useMutation({
    mutationFn: () => {
      if (activeAutoplayJob) {
        return omnixApiClient.cancelJob(activeAutoplayJob.id, 'Stopped from the RPG workspace autoplay control.');
      }

      return omnixApiClient.createJob({
        module: 'rpg',
        type: 'rpg.autoplay',
        resource_class: 'gpu:llm',
        priority: 0,
        input_ref: selectedLiveSessionId ? { session_id: selectedLiveSessionId } : null,
        input_payload: {
          determinism_policy: 'replay_preserving',
          source: 'rpg-workspace',
          turn_budget: 10,
        },
        stages: [
          { id: 'load-session', label: 'Load RPG session', resource_class: 'cpu', status: 'queued' },
          { id: 'plan-turns', label: 'Plan deterministic turns', resource_class: 'gpu:llm', status: 'queued' },
          { id: 'run-turns', label: 'Run autoplay turns', resource_class: 'cpu', status: 'queued' },
          { id: 'write-report', label: 'Write autoplay report', resource_class: 'cpu', status: 'queued' },
        ],
      });
    },
    onSuccess: async () => {
      await invalidateRpgWorkspaceQueries();
    },
  });
  const submitStatus = createJobMutation.isPending ? 'queueing' : createJobMutation.isError ? 'error' : createJobMutation.data?.status ?? 'ready';
  const checkpointControlStatus = createCheckpointMutation.isPending
    ? 'Creating checkpoint…'
    : createCheckpointMutation.isError
      ? 'Checkpoint request failed.'
      : createCheckpointMutation.data?.checkpoint_id
        ? `Checkpoint created: ${createCheckpointMutation.data.checkpoint_id}`
        : undefined;
  const autoplayStatusLabel = autoplayMutation.isPending
    ? 'Updating autoplay…'
    : autoplayMutation.isError
      ? 'Autoplay control failed.'
      : activeAutoplayJob
        ? `${activeAutoplayJob.status} • ${activeAutoplayJob.id}`
        : 'Off';
  const isRefreshingRpgQueries = inventoryQuery.isFetching || jobsQuery.isFetching || assetsQuery.isFetching || reportsQuery.isFetching;
  const selectCommand = (command: string) => setValue('command', command, { shouldDirty: true, shouldValidate: true });

  return (
    <WorkspacePanel className="rpg-workstation">
      <RpgWorkspaceHeader module={module} selectedSessionSummary={selectedSessionSummary} submitStatus={submitStatus} />

      <div className="rpg-layout-controls" aria-label="Workspace layout controls">
        <button
          className="rpg-secondary-button"
          type="button"
          aria-pressed={isPlayerRailCollapsed}
          onClick={() => setIsPlayerRailCollapsed((value) => !value)}
        >
          {isPlayerRailCollapsed ? 'Show player rail' : 'Hide player rail'}
        </button>
        <button
          className="rpg-secondary-button"
          type="button"
          aria-pressed={isWorldRailCollapsed}
          onClick={() => setIsWorldRailCollapsed((value) => !value)}
        >
          {isWorldRailCollapsed ? 'Show world rail' : 'Hide world rail'}
        </button>
      </div>

      <div className={dashboardClassName}>
        {isPlayerRailCollapsed ? null : (
          <RpgPlayerRail
            activeQuests={activeQuests}
            equippedGear={equippedGear}
            heroStats={heroStats}
            heroSummary={heroSummary}
            partyMembers={partyMembers}
          />
        )}

        <main className="rpg-center-stage" aria-label="Story scene and actions">
          <RpgStoryScene heroSummary={heroSummary} recentEvents={recentEvents} selectedSessionSummary={selectedSessionSummary}>
            <RpgActionComposer
              commandRegistration={register('command', { required: true })}
              hasCommandError={Boolean(errors.command)}
              isPending={createJobMutation.isPending}
              onQuickAction={selectCommand}
              onSubmit={handleSubmit((values) => createJobMutation.mutate(values))}
              quickActions={quickActions}
              sessionRegistration={register('sessionId')}
              sessionSummaries={sessionSummaries}
            />
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
          </RpgStoryScene>

          <RpgCombatSurface combat={combatSurface} onSelectCommand={selectCommand} />

          <RpgNarrativeTabs journalDetail={journalDetail} journalEntries={journalEntries} recentEvents={recentEvents} />

          <RpgLoadoutTabs hotbarAbilities={hotbarAbilities} inventoryItems={inventoryItems} onSelectCommand={selectCommand} />
        </main>

        {isWorldRailCollapsed ? null : (
          <RpgWorldRail
            autoplayRunning={Boolean(activeAutoplayJob)}
            autoplayStatusLabel={autoplayStatusLabel}
            checkpointControlStatus={checkpointControlStatus}
            checkpointSummary={checkpointSummary}
            encounter={encounter}
            isAutoplayPending={autoplayMutation.isPending}
            isCreatingCheckpoint={createCheckpointMutation.isPending}
            isRefreshingJobs={isRefreshingRpgQueries}
            jobCards={jobCards}
            npcRelationships={npcRelationships}
            onCreateCheckpoint={() => createCheckpointMutation.mutate()}
            onRefreshJobs={() => void invalidateRpgWorkspaceQueries()}
            onToggleAutoplay={() => autoplayMutation.mutate()}
            reportsHref="/api/reports"
            rpgAssets={rpgAssets}
            rpgJobCount={rpgJobs.length}
            rpgReportCount={rpgReports.length}
            selectedSessionSummary={selectedSessionSummary}
            worldStateRows={worldStateRows}
          />
        )}
      </div>
    </WorkspacePanel>
  );
}
