import { useEffect, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { ApiTimeoutError, omnixApiClient } from '../../api/client';
import { rpgSessionClient, type RpgLoadoutActionRequest, type RpgNewGameRequest } from './api/rpgSessionClient';
import type { HermesRpgApprovedFlowResponse } from './api/hermesRpgApprovedFlowClient';
import type { OmnixModuleDefinition } from '../../app/modules';
import { WorkspacePanel } from '../../design/primitives';
import { FeatureSubmitFeedback, FeatureValidationMessage } from '../../shared/FeatureSubmitFeedback';
import { RpgActionComposer } from './RpgActionComposer';
import { RpgCampaignMenu } from './RpgCampaignMenu';
import { useRpgHermesAssist } from './useRpgHermesAssist';
import { useRpgResumeAfterAway } from './useRpgResumeAfterAway';
import { RpgCombatSurface } from './RpgCombatSurface';
import { RpgCreateCampaignWizard } from './RpgCreateCampaignWizard';
import { RpgDeveloperTools } from './RpgDeveloperTools';
import { RpgLiveDataStatus } from './RpgLiveDataStatus';
import { buildRpgLiveDataCards } from './rpgLiveDataCards';
import { RpgLoadoutTabs } from './RpgLoadoutTabs';
import { RpgNarrativeTabs } from './RpgNarrativeTabs';
import { RpgPlayerRail } from './RpgPlayerRail';
import { RpgStoryScene } from './RpgStoryScene';
import { RpgWorkspaceHeader } from './RpgWorkspaceHeader';
import { RpgWorldRail } from './RpgWorldRail';
import { buildRpgFight } from './rpgCombatState';
import { createRpgWorkspaceState } from './rpgUiState';
import './RpgWorkspace.css';
import './RpgResponsivePolish.css';
import { ACTIVE_JOB_STATUSES, RPG_TURN_QUEUE_TIMEOUT_MS, RPG_TURN_RECOVERY_WINDOW_MS, buildSubmittedTurnStoryMessages, isRpgTurnJobType, readStoredDeveloperTools, readStoredRpgSessionId, timestampMs, writeStoredDeveloperTools, writeStoredRpgSessionId } from './rpgWorkspaceSupport';
import type { PendingRpgTurnSubmission, RpgFormValues } from './rpgWorkspaceSupport';

export function RpgWorkspace({ module }: { module: OmnixModuleDefinition }) {
  const queryClient = useQueryClient();
  const [isPlayerRailCollapsed, setIsPlayerRailCollapsed] = useState(false);
  const [isWorldRailCollapsed, setIsWorldRailCollapsed] = useState(false);
  const [isLiveDataExpanded, setIsLiveDataExpanded] = useState(false);
  const [campaignMenuHost, setCampaignMenuHost] = useState<HTMLElement | null>(null);
  const [latestHermesExecutionResult, setLatestHermesExecutionResult] = useState<HermesRpgApprovedFlowResponse | null>(null);
  // Hermes sequence tools and job ids are for developers; players see the story (RQ-7.1).
  const [developerTools, setDeveloperTools] = useState(readStoredDeveloperTools);
  const toggleDeveloperTools = () => {
    setDeveloperTools((value) => {
      writeStoredDeveloperTools(!value);
      return !value;
    });
  };
  const inventoryQuery = useQuery({
    queryKey: ['feature', 'rpg', 'replay-inventory'],
    queryFn: () => rpgSessionClient.listRpgSessionSummaries(),
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
  const trustedUnindexedSessionIdsRef = useRef<Set<string>>(new Set());
  const {
    register,
    handleSubmit,
    reset,
    setValue,
    watch,
    formState: { errors },
  } = useForm<RpgFormValues>({
    defaultValues: { sessionId: readStoredRpgSessionId(), command: '' },
  });
  const selectedSessionId = watch('sessionId');
  const summaryState = createRpgWorkspaceState({
    inventory: inventoryQuery.data,
    jobs: jobsQuery.data,
    assets: assetsQuery.data,
    reports: reportsQuery.data,
    selectedSessionId,
  });
  const requestedSessionId = selectedSessionId?.trim() ?? '';
  const selectedSessionIsIndexed = Boolean(
    requestedSessionId && summaryState.sessionSummaries.some((session) => session.source === 'live' && session.id === requestedSessionId),
  );
  const fallbackLiveSessionId = summaryState.sessionSummaries.find((session) => session.source === 'live')?.id ?? null;
  const selectedSummarySessionId = requestedSessionId || fallbackLiveSessionId;
  useEffect(() => {
    if (!requestedSessionId && fallbackLiveSessionId) {
      setValue('sessionId', fallbackLiveSessionId, { shouldValidate: true });
    }
  }, [fallbackLiveSessionId, requestedSessionId, setValue]);
  const selectedSessionQuery = useQuery({
    queryKey: ['feature', 'rpg', 'session', selectedSummarySessionId],
    queryFn: () => rpgSessionClient.getRpgSession(selectedSummarySessionId ?? ''),
    enabled: Boolean(selectedSummarySessionId),
  });
  useEffect(() => {
    if (!requestedSessionId || !inventoryQuery.data || selectedSessionIsIndexed || !selectedSessionQuery.isError) {
      return;
    }
    if (trustedUnindexedSessionIdsRef.current.has(requestedSessionId)) {
      return;
    }

    setValue('sessionId', fallbackLiveSessionId ?? '', { shouldValidate: true });
  }, [
    fallbackLiveSessionId,
    inventoryQuery.data,
    requestedSessionId,
    selectedSessionIsIndexed,
    selectedSessionQuery.isError,
    setValue,
  ]);
  const {
    heroSummary,
    heroStats,
    survival,
    equippedGear,
    partyMembers,
    activeQuests,
    quickActions,
    storyMessages,
    recentEvents,
    journalEntries,
    narrativeLogEntries,
    journalDetail,
    inventoryItems,
    hotbarAbilities,
    worldStateRows,
    npcRelationships,
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
  const fight = buildRpgFight(selectedSessionQuery.data?.session, heroSummary.name);
  const selectedLiveSessionId = selectedSessionSummary.source === 'live' ? selectedSessionSummary.id : null;
  const selectedLiveSessionIsIndexed = Boolean(
    selectedLiveSessionId && sessionSummaries.some((session) => session.source === 'live' && session.id === selectedLiveSessionId),
  );
  useEffect(() => {
    if (selectedLiveSessionId && selectedLiveSessionIsIndexed) {
      writeStoredRpgSessionId(selectedLiveSessionId);
      return;
    }

    if (inventoryQuery.data && !fallbackLiveSessionId) {
      writeStoredRpgSessionId(null);
    }
  }, [fallbackLiveSessionId, inventoryQuery.data, selectedLiveSessionId, selectedLiveSessionIsIndexed]);
  const refreshedTurnJobRef = useRef<string | null>(null);
  const pendingTurnSubmissionRef = useRef<PendingRpgTurnSubmission | null>(null);
  const latestCompletedTurnJob = rpgJobs
    .filter((job) => {
      const sessionId = typeof job.input_ref?.session_id === 'string' ? job.input_ref.session_id : null;
      return isRpgTurnJobType(job.type) && job.status === 'completed' && sessionId === selectedLiveSessionId;
    })
    .sort((left, right) => right.updated_at.localeCompare(left.updated_at))[0];
  const latestCompletedTurnJobId = latestCompletedTurnJob?.id;
  const refetchSelectedSession = selectedSessionQuery.refetch;
  const refetchInventory = inventoryQuery.refetch;
  useEffect(() => {
    if (!latestCompletedTurnJobId || refreshedTurnJobRef.current === latestCompletedTurnJobId) return;
    refreshedTurnJobRef.current = latestCompletedTurnJobId;
    void Promise.all([
      refetchSelectedSession(),
      refetchInventory(),
      queryClient.invalidateQueries({ queryKey: ['feature', 'rpg', 'hermes-suggestions', selectedLiveSessionId] }),
      queryClient.invalidateQueries({ queryKey: ['feature', 'rpg', 'hermes-route-decision', 'rpg'] }),
      queryClient.invalidateQueries({ queryKey: ['feature', 'rpg', 'hermes-turn-readout', selectedLiveSessionId] }),
    ]);
  }, [latestCompletedTurnJobId, queryClient, refetchInventory, refetchSelectedSession, selectedLiveSessionId]);
  const activeAutoplayJob = rpgJobs.find((job) => job.type === 'rpg.autoplay' && ACTIVE_JOB_STATUSES.has(job.status));
  const liveDataStatusCards = buildRpgLiveDataCards({
    inventory: inventoryQuery, sessionCount: inventoryQuery.data?.sessions?.length ?? 0,
    jobs: jobsQuery, jobCount: rpgJobs.length,
    assets: assetsQuery, assetCount: rpgAssets.length,
    reports: reportsQuery, reportCount: rpgReports.length,
  });
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
      // The loadout's skills, abilities and effects change with story turns too.
      queryClient.invalidateQueries({ queryKey: ['feature', 'rpg', 'ability-tree-session'] }),
      queryClient.invalidateQueries({ queryKey: ['feature', 'rpg', 'hermes-suggestions'] }),
      queryClient.invalidateQueries({ queryKey: ['feature', 'rpg', 'hermes-route-decision'] }),
      queryClient.invalidateQueries({ queryKey: ['feature', 'rpg', 'hermes-turn-readout'] }),
      queryClient.invalidateQueries({ queryKey: ['feature', 'rpg', 'hermes-execution-ledger'] }),
      queryClient.invalidateQueries({ queryKey: ['feature', 'rpg', 'hermes-sequence-state'] }),
      queryClient.invalidateQueries({ queryKey: ['platform', 'jobs'] }),
      queryClient.invalidateQueries({ queryKey: ['platform', 'assets'] }),
      queryClient.invalidateQueries({ queryKey: ['platform', 'reports'] }),
    ]);
  };
  const {
    activeHermesSequenceJob,
    hermesRouteDecision,
    hermesSequenceJobMutation,
    hermesSuggestionState,
    hermesSuggestions,
    hermesTurnReadout,
    responseOptions,
  } = useRpgHermesAssist({
    selectedLiveSessionId, selectedSessionSummary, quickActions, latestCompletedTurnJobId, rpgJobs,
    onJobChanged: invalidateRpgWorkspaceQueries,
  });
  // After a turn run outside the composer's job (an undo, a return to a save point, coming back after time away).
  const refreshAfterTurn = () => {
    void queryClient.invalidateQueries({ queryKey: ['feature', 'rpg', 'session', selectedLiveSessionId] });
    void invalidateRpgWorkspaceQueries();
  };
  useRpgResumeAfterAway(
    selectedLiveSessionId ?? '',
    sessionSummaries.find((session) => session.id === selectedLiveSessionId)?.lastPlayedMs,
    refreshAfterTurn,
  );
  const createJobMutation = useMutation({
    mutationFn: (values: RpgFormValues) => {
      const sessionId = values.sessionId || selectedLiveSessionId;
      return rpgSessionClient.submitTurnJob(
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
            'The RPG turn queue request is taking longer than expected. The workspace will keep checking the RPG job queue for this turn.',
        },
      );
    },
    onMutate: (values) => {
      pendingTurnSubmissionRef.current = {
        command: values.command.trim(),
        sessionId: values.sessionId || selectedLiveSessionId || '',
        submittedAt: Date.now(),
      };
    },
    onSuccess: (_job, values) => {
      const sessionId = values.sessionId || selectedLiveSessionId || '';
      if (sessionId) {
        writeStoredRpgSessionId(sessionId);
      }
      reset({ sessionId, command: '' });
      void invalidateRpgWorkspaceQueries();
    },
  });
  const activeSubmittedTurnJobId = createJobMutation.data?.id ?? null;
  const submittedTurnJobQuery = useQuery({
    queryKey: ['platform', 'jobs', 'submitted-rpg-turn', activeSubmittedTurnJobId],
    queryFn: () => omnixApiClient.getJob(activeSubmittedTurnJobId ?? ''),
    enabled: Boolean(activeSubmittedTurnJobId),
    refetchInterval: activeSubmittedTurnJobId ? 1500 : false,
  });
  const submittedTurnJobFromQuery = submittedTurnJobQuery.data;
  useEffect(() => {
    if (
      !submittedTurnJobFromQuery || !isRpgTurnJobType(submittedTurnJobFromQuery.type)
      || submittedTurnJobFromQuery.status !== 'completed'
      || refreshedTurnJobRef.current === submittedTurnJobFromQuery.id
    ) {
      return;
    }
    refreshedTurnJobRef.current = submittedTurnJobFromQuery.id;
    void Promise.all([
      refetchSelectedSession(),
      refetchInventory(),
      jobsQuery.refetch(),
      queryClient.invalidateQueries({ queryKey: ['feature', 'rpg', 'hermes-suggestions', selectedLiveSessionId] }),
      queryClient.invalidateQueries({ queryKey: ['feature', 'rpg', 'hermes-route-decision', 'rpg'] }),
      queryClient.invalidateQueries({ queryKey: ['feature', 'rpg', 'hermes-turn-readout', selectedLiveSessionId] }),
    ]);
  }, [jobsQuery, queryClient, refetchInventory, refetchSelectedSession, selectedLiveSessionId, submittedTurnJobFromQuery]);
  const loadoutActionMutation = useMutation({
    mutationFn: ({ sessionId, request }: { sessionId: string; request: RpgLoadoutActionRequest }) => rpgSessionClient.applyRpgLoadoutAction(sessionId, request),
    onSuccess: refreshAfterTurn, // a pack action is a turn
  });
  const createCampaignMutation = useMutation({
    mutationFn: (request: RpgNewGameRequest) => rpgSessionClient.createRpgNewGame(request),
    onSuccess: (result) => {
      if (result.ok && result.session_id) {
        trustedUnindexedSessionIdsRef.current.add(result.session_id);
        if (result.session) {
          queryClient.setQueryData(['feature', 'rpg', 'session', result.session_id], result);
        }
        writeStoredRpgSessionId(result.session_id);
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
  const recoveredSubmittedTurnJob = (() => {
    const pending = pendingTurnSubmissionRef.current;
    if (!pending) return undefined;
    const recoveryStart = pending.submittedAt - 5_000;
    const recoveryEnd = pending.submittedAt + RPG_TURN_RECOVERY_WINDOW_MS;
    return rpgJobs
      .filter((job) => {
        const sessionId = typeof job.input_ref?.session_id === 'string' ? job.input_ref.session_id : '';
        const command = typeof job.input_payload?.command === 'string' ? job.input_payload.command.trim() : '';
        const createdAt = timestampMs(job.created_at);
        return isRpgTurnJobType(job.type)
          && sessionId === pending.sessionId
          && command === pending.command
          && (!createdAt || (createdAt >= recoveryStart && createdAt <= recoveryEnd));
      })
      .sort((left, right) => timestampMs(right.created_at) - timestampMs(left.created_at))[0];
  })();
  const submittedTurnJob = createJobMutation.data
    ? submittedTurnJobFromQuery ?? rpgJobs.find((job) => job.id === createJobMutation.data.id) ?? createJobMutation.data
    : recoveredSubmittedTurnJob;
  const submittedTurnFailed = submittedTurnJob
    ? ['failed', 'canceled', 'stale'].includes(submittedTurnJob.status)
    : false;
  const submittedTurnFailureMessage = submittedTurnFailed
    ? `RPG turn ${submittedTurnJob?.status}: ${submittedTurnJob?.error?.message ?? 'The turn did not produce a response.'}`
    : '';
  const recoveredAfterQueueTimeout = Boolean(!createJobMutation.data && createJobMutation.isError && recoveredSubmittedTurnJob);
  const isReconcilingTimedOutTurn = Boolean(createJobMutation.error instanceof ApiTimeoutError && !submittedTurnJob);
  const submitStatus = createJobMutation.isPending
    ? 'queueing'
    : submittedTurnFailed
      ? 'error'
      : submittedTurnJob
        ? submittedTurnJob.status
        : isReconcilingTimedOutTurn
          ? 'reconciling'
        : createJobMutation.isError
          ? 'error'
          : createJobMutation.data?.status ?? 'ready';
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
  const submittedTurnStoryMessages = buildSubmittedTurnStoryMessages(
    submittedTurnJob,
    heroSummary.name,
    heroSummary.avatar,
    selectedLiveSessionId,
  );
  const missingSubmittedTurnMessages = submittedTurnStoryMessages.filter(
    (submitted) => !storyMessages.some((message) => (
      (submitted.interactionId && submitted.interactionId === message.interactionId)
      || submitted.text === message.text
    )),
  );
  const visibleStoryMessages = missingSubmittedTurnMessages.length
    ? [...storyMessages, ...missingSubmittedTurnMessages].slice(-40)
    : storyMessages;

  return (
    <WorkspacePanel labelledBy="module-title" className="rpg-workstation">
      <h2 id="module-title" className="workspace-module-heading">{module.label}</h2>
      <header className="rpg-unified-header" aria-label="Campaign menu header">
        <div className="rpg-campaign-menu-host" ref={setCampaignMenuHost} />
        <RpgWorkspaceHeader
          isLiveDataExpanded={isLiveDataExpanded}
          isPlayerRailCollapsed={isPlayerRailCollapsed}
          isWorldRailCollapsed={isWorldRailCollapsed}
          module={module}
          developerTools={developerTools}
          onToggleDeveloperTools={toggleDeveloperTools}
          onToggleLiveData={() => setIsLiveDataExpanded((value) => !value)}
          onTogglePlayerRail={() => setIsPlayerRailCollapsed((value) => !value)}
          onToggleWorldRail={() => setIsWorldRailCollapsed((value) => !value)}
          selectedSessionSummary={selectedSessionSummary}
          submitStatus={submitStatus}
        />
      </header>

      <RpgLiveDataStatus
        cards={liveDataStatusCards}
        expanded={isLiveDataExpanded}
        hideWhenCollapsed
        onExpandedChange={setIsLiveDataExpanded}
        showToggle={false}
      />

      <div className={dashboardClassName}>
        {isPlayerRailCollapsed ? null : (
          <RpgPlayerRail
            activeQuests={activeQuests}
            className="rpg-rail-expanded"
            equippedGear={equippedGear}
            heroStats={heroStats}
            heroSummary={heroSummary}
            hermesRouteDecision={hermesRouteDecision}
            hermesSuggestionState={hermesSuggestionState}
            hermesSuggestions={hermesSuggestions}
            hermesTurnReadout={hermesTurnReadout}
            onApprovedFlowAccepted={async (result) => {
              setLatestHermesExecutionResult(result);
              await invalidateRpgWorkspaceQueries();
            }}
            onSelectCommand={selectCommand}
            partyMembers={partyMembers}
            survival={survival}
          />
        )}

        {/* A section, not <main>: the app shell's canvas is the page's main region (RQ-7.6, axe). */}
        <section className="rpg-center-stage" aria-label="Story scene and actions">
          <RpgStoryScene
            developerTools={developerTools}
            heroSummary={heroSummary}
            recentEvents={recentEvents}
            selectedSessionSummary={selectedSessionSummary}
            storyMessages={visibleStoryMessages}
          >
            <RpgCampaignMenu
              campaignMenuHost={campaignMenuHost}
              isPending={createJobMutation.isPending || isReconcilingTimedOutTurn}
              liveSessionId={selectedLiveSessionId ?? ''}
              onTurnApplied={refreshAfterTurn}
              renderNewCampaign={(closeLauncher) => (
                <RpgCreateCampaignWizard
                  onCreateCampaign={(request) => createCampaignMutation.mutateAsync(request)}
                  onEnterWorld={closeLauncher}
                />
              )}
              selectedSessionId={selectedSessionId}
              sessionRegistration={register('sessionId')}
              sessionSummaries={sessionSummaries}
            />
            <RpgActionComposer
              commandRegistration={register('command', { required: true })}
              hasCommandError={Boolean(errors.command)}
              isPending={createJobMutation.isPending || isReconcilingTimedOutTurn}
              liveSessionId={selectedLiveSessionId ?? ''}
              onQuickAction={selectCommand}
              onSubmit={handleSubmit((values) => createJobMutation.mutate(values))}
              onTurnApplied={refreshAfterTurn}
              quickActions={responseOptions}
              selectedSessionId={selectedSessionId}
              sessionRegistration={register('sessionId')}
              sessionSummaries={sessionSummaries}
            />
            <FeatureValidationMessage show={Boolean(errors.command)} message="Type what you want to do first." />
            <FeatureValidationMessage show={submittedTurnFailed} message={submittedTurnFailureMessage} />
            <FeatureSubmitFeedback
              error={recoveredAfterQueueTimeout || isReconcilingTimedOutTurn ? null : createJobMutation.error}
              errorPrefix="Your turn"
              isError={createJobMutation.isError && !recoveredAfterQueueTimeout && !isReconcilingTimedOutTurn}
              isPending={createJobMutation.isPending || isReconcilingTimedOutTurn}
              jobId={submittedTurnFailed || !developerTools ? undefined : submittedTurnJob?.id}
              pendingMessage={isReconcilingTimedOutTurn ? 'Still checking on your turn…' : 'Sending your turn…'}
              successPrefix="Turn job"
            />
          </RpgStoryScene>

          {developerTools ? (
            <RpgDeveloperTools
              activeJob={activeHermesSequenceJob}
              executionResult={latestHermesExecutionResult}
              isPending={hermesSequenceJobMutation.isPending}
              onJobAction={(action) => hermesSequenceJobMutation.mutate(action)}
            />
          ) : null}

          <RpgCombatSurface fight={fight} />

          <RpgNarrativeTabs journalDetail={journalDetail} journalEntries={journalEntries} logEntries={narrativeLogEntries} recentEvents={recentEvents} />

          <RpgLoadoutTabs
            hotbarAbilities={hotbarAbilities}
            inventoryItems={inventoryItems}
            isApplyingLoadoutAction={loadoutActionMutation.isPending}
            onApplyLoadoutAction={applyLoadoutAction}
            onSelectCommand={selectCommand}
            onSubmitCommand={(command) => createJobMutation.mutate({ sessionId: selectedSessionId, command })}
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
        </section>

        {isWorldRailCollapsed ? null : (
          <RpgWorldRail
            developerTools={developerTools}
            autoplayRunning={Boolean(activeAutoplayJob)}
            autoplayStatusLabel={autoplayStatusLabel}
            className="rpg-rail-expanded"
            checkpointSummary={checkpointSummary}
            isAutoplayPending={autoplayMutation.isPending}
            isRefreshingJobs={isRefreshingRpgQueries}
            jobCards={jobCards}
            npcRelationships={npcRelationships}
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
