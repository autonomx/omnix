import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { omnixApiClient, type RpgLoadoutActionRequest, type RpgNewGameRequest } from '../../api/client';
import type { OmnixModuleDefinition } from '../../app/modules';
import { WorkspacePanel } from '../../design/primitives';
import { FeatureSubmitFeedback, FeatureValidationMessage } from '../shared/FeatureSubmitFeedback';
import { RpgActionComposer } from './RpgActionComposer';
import { RpgCombatSurface } from './RpgCombatSurface';
import { RpgCreateCampaignWizard } from './RpgCreateCampaignWizard';
import { RpgLiveDataStatus, type RpgLiveDataStatusCard } from './RpgLiveDataStatus';
import { RpgLoadoutTabs } from './RpgLoadoutTabs';
import { RpgNarrativeTabs } from './RpgNarrativeTabs';
import { RpgPlayerRail } from './RpgPlayerRail';
import { RpgStoryScene } from './RpgStoryScene';
import { RpgWorkspaceHeader } from './RpgWorkspaceHeader';
import { RpgWorldRail } from './RpgWorldRail';
import { createRpgCombatSurfaceState } from './rpgCombatState';
import { createRpgWorkspaceState } from './rpgUiState';
import './RpgWorkspace.css';
import './RpgResponsivePolish.css';

interface RpgFormValues {
  sessionId: string;
  command: string;
}

const ACTIVE_JOB_STATUSES = new Set(['queued', 'leased', 'running', 'waiting', 'retrying', 'cancel_requested']);
const RPG_TURN_QUEUE_TIMEOUT_MS = 10_000;

function formatQueryError(error: unknown) {
  if (error instanceof Error) {
    return error.message;
  }

  return 'Request failed before the RPG workspace could read this source.';
}

export function RpgWorkspace({ module }: { module: OmnixModuleDefinition }) {
  const queryClient = useQueryClient();
  const [isPlayerRailCollapsed, setIsPlayerRailCollapsed] = useState(false);
  const [isWorldRailCollapsed, setIsWorldRailCollapsed] = useState(false);
  const [isPlayerRailFullSize, setIsPlayerRailFullSize] = useState(true);
  const [isWorldRailFullSize, setIsWorldRailFullSize] = useState(true);
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
  const summaryState = createRpgWorkspaceState({
    inventory: inventoryQuery.data,
    jobs: jobsQuery.data,
    assets: assetsQuery.data,
    reports: reportsQuery.data,
    selectedSessionId,
  });
  const selectedSummarySessionId = summaryState.selectedSessionSummary.source === 'live' ? summaryState.selectedSessionSummary.id : null;
  useEffect(() => {
    if (!selectedSessionId && selectedSummarySessionId) {
      setValue('sessionId', selectedSummarySessionId, { shouldValidate: true });
    }
  }, [selectedSessionId, selectedSummarySessionId, setValue]);
  const selectedSessionQuery = useQuery({
    queryKey: ['feature', 'rpg', 'session', selectedSummarySessionId],
    queryFn: () => omnixApiClient.getRpgSession(selectedSummarySessionId ?? ''),
    enabled: Boolean(selectedSummarySessionId),
  });
  const {
    heroSummary,
    heroStats,
    equippedGear,
    partyMembers,
    activeQuests,
    quickActions,
    storyMessages,
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
    selectedSession: selectedSessionQuery.data?.session,
  });
  const combatSurface = createRpgCombatSurfaceState({ encounter, heroSummary, partyMembers });
  const selectedLiveSessionId = selectedSessionSummary.source === 'live' ? selectedSessionSummary.id : null;
  const activeAutoplayJob = rpgJobs.find((job) => job.type === 'rpg.autoplay' && ACTIVE_JOB_STATUSES.has(job.status));
  const hasLiveSessions = (inventoryQuery.data?.sessions?.length ?? 0) > 0;
  const liveDataStatusCards: RpgLiveDataStatusCard[] = [
    {
      id: 'sessions',
      label: 'Sessions',
      state: inventoryQuery.isError
        ? 'error'
        : inventoryQuery.isPending && !inventoryQuery.data
          ? 'loading'
          : inventoryQuery.isFetching && inventoryQuery.data
            ? 'refreshing'
            : hasLiveSessions
              ? 'ready'
              : 'empty',
      detail: inventoryQuery.isError
        ? formatQueryError(inventoryQuery.error)
        : inventoryQuery.isPending && !inventoryQuery.data
          ? 'Loading replay persistence inventory and campaign sessions.'
          : inventoryQuery.isFetching && inventoryQuery.data
            ? 'Refreshing the selected session and checkpoint metadata.'
            : hasLiveSessions
              ? `${inventoryQuery.data?.sessions?.length ?? 0} saved session${(inventoryQuery.data?.sessions?.length ?? 0) === 1 ? '' : 's'} available.`
              : 'No saved RPG sessions found. Preview fallback remains active until a campaign is created.',
    },
    {
      id: 'jobs',
      label: 'Jobs',
      state: jobsQuery.isError
        ? 'error'
        : jobsQuery.isPending && !jobsQuery.data
          ? 'loading'
          : jobsQuery.isFetching && jobsQuery.data
            ? 'refreshing'
            : rpgJobs.length
              ? 'ready'
              : 'empty',
      detail: jobsQuery.isError
        ? formatQueryError(jobsQuery.error)
        : jobsQuery.isPending && !jobsQuery.data
          ? 'Loading shared job queue state for RPG turns and autoplay.'
          : jobsQuery.isFetching && jobsQuery.data
            ? 'Polling background RPG jobs.'
            : rpgJobs.length
              ? `${rpgJobs.length} RPG job${rpgJobs.length === 1 ? '' : 's'} visible in the workspace.`
              : 'No live RPG jobs. Preview job cards keep the rail layout stable.',
    },
    {
      id: 'checkpoints',
      label: 'Checkpoints',
      state: assetsQuery.isError
        ? 'error'
        : assetsQuery.isPending && !assetsQuery.data
          ? 'loading'
          : assetsQuery.isFetching && assetsQuery.data
            ? 'refreshing'
            : rpgAssets.length
              ? 'ready'
              : 'empty',
      detail: assetsQuery.isError
        ? formatQueryError(assetsQuery.error)
        : assetsQuery.isPending && !assetsQuery.data
          ? 'Loading RPG checkpoint and report assets.'
          : assetsQuery.isFetching && assetsQuery.data
            ? 'Refreshing asset metadata for checkpoint/report links.'
            : rpgAssets.length
              ? `${rpgAssets.length} RPG asset${rpgAssets.length === 1 ? '' : 's'} found for checkpoints or reports.`
              : 'No RPG checkpoint/report assets found yet.',
    },
    {
      id: 'reports',
      label: 'Reports',
      state: reportsQuery.isError
        ? 'error'
        : reportsQuery.isPending && !reportsQuery.data
          ? 'loading'
          : reportsQuery.isFetching && reportsQuery.data
            ? 'refreshing'
            : rpgReports.length
              ? 'ready'
              : 'empty',
      detail: reportsQuery.isError
        ? formatQueryError(reportsQuery.error)
        : reportsQuery.isPending && !reportsQuery.data
          ? 'Loading generated report index.'
          : reportsQuery.isFetching && reportsQuery.data
            ? 'Refreshing RPG report availability.'
            : rpgReports.length
              ? `${rpgReports.length} RPG report${rpgReports.length === 1 ? '' : 's'} ready to open.`
              : 'No RPG reports found. Run autoplay or export a report to populate this source.',
    },
  ];
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
    mutationFn: (values: RpgFormValues) => {
      const sessionId = values.sessionId || selectedLiveSessionId;
      return omnixApiClient.createJob(
        {
          module: 'rpg',
          type: 'rpg.turn',
          resource_class: 'gpu:llm',
          priority: 0,
          input_ref: sessionId ? { session_id: sessionId } : null,
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
        },
        {
          timeoutMs: RPG_TURN_QUEUE_TIMEOUT_MS,
          timeoutMessage:
            'Gateway did not acknowledge the RPG turn queue request within 10s. The turn may still be running; refresh RPG jobs or restart the gateway if this repeats.',
        },
      );
    },
    onSuccess: (_job, values) => {
      reset({ sessionId: values.sessionId || selectedLiveSessionId || '', command: '' });
      void invalidateRpgWorkspaceQueries();
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
    onSuccess: () => {
      void invalidateRpgWorkspaceQueries();
    },
  });
  const loadoutActionMutation = useMutation({
    mutationFn: ({ sessionId, request }: { sessionId: string; request: RpgLoadoutActionRequest }) => omnixApiClient.applyRpgLoadoutAction(sessionId, request),
    onSuccess: async () => {
      await invalidateRpgWorkspaceQueries();
    },
  });
  const createCampaignMutation = useMutation({
    mutationFn: (request: RpgNewGameRequest) => omnixApiClient.createRpgNewGame(request),
    onSuccess: (result) => {
      if (result.ok && result.session_id) {
        if (result.session) {
          queryClient.setQueryData(['feature', 'rpg', 'session', result.session_id], result);
        }
        setValue('sessionId', result.session_id, { shouldDirty: true, shouldValidate: true });
      }
      void invalidateRpgWorkspaceQueries();
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
  const applyLoadoutAction = (request: RpgLoadoutActionRequest) => {
    if (!selectedLiveSessionId) {
      selectCommand('Select or create a live RPG session before using inventory or abilities.');
      return;
    }
    loadoutActionMutation.mutate({ sessionId: selectedLiveSessionId, request });
  };

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
          aria-pressed={isPlayerRailFullSize}
          disabled={isPlayerRailCollapsed}
          onClick={() => setIsPlayerRailFullSize((value) => !value)}
        >
          {isPlayerRailFullSize ? 'Contain player rail' : 'Full-size player rail'}
        </button>
        <button
          className="rpg-secondary-button"
          type="button"
          aria-pressed={isWorldRailCollapsed}
          onClick={() => setIsWorldRailCollapsed((value) => !value)}
        >
          {isWorldRailCollapsed ? 'Show world rail' : 'Hide world rail'}
        </button>
        <button
          className="rpg-secondary-button"
          type="button"
          aria-pressed={isWorldRailFullSize}
          disabled={isWorldRailCollapsed}
          onClick={() => setIsWorldRailFullSize((value) => !value)}
        >
          {isWorldRailFullSize ? 'Contain world rail' : 'Full-size world rail'}
        </button>
      </div>

      <RpgLiveDataStatus cards={liveDataStatusCards} />

      <div className={dashboardClassName}>
        {isPlayerRailCollapsed ? null : (
          <RpgPlayerRail
            activeQuests={activeQuests}
            className={isPlayerRailFullSize ? 'rpg-rail-full-size' : undefined}
            equippedGear={equippedGear}
            heroStats={heroStats}
            heroSummary={heroSummary}
            partyMembers={partyMembers}
          />
        )}

        <main className="rpg-center-stage" aria-label="Story scene and actions">
          <RpgStoryScene
            heroSummary={heroSummary}
            recentEvents={recentEvents}
            selectedSessionSummary={selectedSessionSummary}
            storyMessages={storyMessages}
          >
            <RpgActionComposer
              canSaveGame={Boolean(selectedLiveSessionId)}
              commandRegistration={register('command', { required: true })}
              hasCommandError={Boolean(errors.command)}
              isPending={createJobMutation.isPending}
              onQuickAction={selectCommand}
              onSaveGame={async () => {
                const checkpoint = await createCheckpointMutation.mutateAsync();
                return checkpoint.checkpoint_id;
              }}
              onSubmit={handleSubmit((values) => createJobMutation.mutate(values))}
              quickActions={quickActions}
              renderNewCampaign={(closeLauncher) => (
                <RpgCreateCampaignWizard
                  onCreateCampaign={(request) => createCampaignMutation.mutateAsync(request)}
                  onSelectCommand={(command) => {
                    selectCommand(command);
                    closeLauncher();
                  }}
                />
              )}
              selectedSessionId={selectedSessionId}
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

          <RpgLoadoutTabs
            hotbarAbilities={hotbarAbilities}
            inventoryItems={inventoryItems}
            isApplyingLoadoutAction={loadoutActionMutation.isPending}
            onApplyLoadoutAction={applyLoadoutAction}
            onSelectCommand={selectCommand}
            selectedSessionId={selectedLiveSessionId}
          />
          <FeatureSubmitFeedback
            error={loadoutActionMutation.error}
            errorPrefix="RPG loadout action"
            isError={loadoutActionMutation.isError}
            isPending={loadoutActionMutation.isPending}
            pendingMessage="Applying deterministic loadout action…"
            successPrefix="RPG loadout action applied"
          />
        </main>

        {isWorldRailCollapsed ? null : (
          <RpgWorldRail
            autoplayRunning={Boolean(activeAutoplayJob)}
            autoplayStatusLabel={autoplayStatusLabel}
            className={isWorldRailFullSize ? 'rpg-rail-full-size' : undefined}
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
