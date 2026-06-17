import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { omnixApiClient } from '../../api/client';
import type { OmnixModuleDefinition } from '../../app/modules';
import { OmnixStatusPill, WorkspacePanel } from '../../design/primitives';
import { FeatureSubmitFeedback, FeatureValidationMessage } from '../shared/FeatureSubmitFeedback';
import { RpgActionComposer } from './RpgActionComposer';
import { RpgLoadoutTabs } from './RpgLoadoutTabs';
import { RpgNarrativeTabs } from './RpgNarrativeTabs';
import { RpgPlayerRail } from './RpgPlayerRail';
import { RpgStoryScene } from './RpgStoryScene';
import { RpgWorldRail } from './RpgWorldRail';
import { createRpgWorkspaceState } from './rpgUiState';
import './RpgWorkspace.css';

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
    <WorkspacePanel className="rpg-workstation">
      <header className="rpg-workstation-header">
        <div>
          <p className="eyebrow">Feature module</p>
          <h2 id="module-title">{module.label} mode</h2>
          <p>{module.summary}</p>
        </div>
        <div className="rpg-header-pills" aria-label="RPG runtime status">
          <OmnixStatusPill>Engine: {submitStatus}</OmnixStatusPill>
          <OmnixStatusPill>Session: {selectedSessionSummary.title}</OmnixStatusPill>
          <OmnixStatusPill>Replay-preserving</OmnixStatusPill>
          <code>{module.route}</code>
        </div>
      </header>

      <div className="rpg-dashboard-grid">
        <RpgPlayerRail
          activeQuests={activeQuests}
          equippedGear={equippedGear}
          heroStats={heroStats}
          heroSummary={heroSummary}
          partyMembers={partyMembers}
        />

        <main className="rpg-center-stage" aria-label="Story scene and actions">
          <RpgStoryScene heroSummary={heroSummary} recentEvents={recentEvents} selectedSessionSummary={selectedSessionSummary}>
            <RpgActionComposer
              commandRegistration={register('command', { required: true })}
              hasCommandError={Boolean(errors.command)}
              isPending={createJobMutation.isPending}
              onQuickAction={(command) => setValue('command', command, { shouldDirty: true, shouldValidate: true })}
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

          <RpgNarrativeTabs journalDetail={journalDetail} journalEntries={journalEntries} recentEvents={recentEvents} />

          <RpgLoadoutTabs hotbarAbilities={hotbarAbilities} inventoryItems={inventoryItems} />
        </main>

        <RpgWorldRail
          checkpointSummary={checkpointSummary}
          encounter={encounter}
          jobCards={jobCards}
          npcRelationships={npcRelationships}
          rpgAssets={rpgAssets}
          rpgJobCount={rpgJobs.length}
          rpgReportCount={rpgReports.length}
          selectedSessionSummary={selectedSessionSummary}
          worldStateRows={worldStateRows}
        />
      </div>
    </WorkspacePanel>
  );
}
