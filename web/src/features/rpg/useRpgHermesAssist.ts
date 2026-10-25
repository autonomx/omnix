import { useMutation, useQuery } from '@tanstack/react-query';
import { omnixApiClient, type JobRecord } from '../../api/client';
import { getHermesRouteDecision, getHermesRpgSuggestions, readHermesRpgTurn } from './api/hermesClient';
import { checkHermesRpgSequence } from './api/hermesRpgSequenceClient';
import { hermesSequencePreviewModel } from './hermesSequencePreviewModel';
import { buildHermesSequenceReviewRequest } from './hermesSequenceReviewRequest';
import { rpgAssistStateFromItems } from './rpgAssistState';
import { useLatestRpgTurnOffers } from './rpgTurnOffers';
import { createRpgTurnReadoutPreview } from './rpgTurnReadoutState';
import { quickActionIcon } from './rpgUiRecords';
import type { RpgQuickActionPreview, RpgSessionSummaryPreview } from './rpgUiTypes';
import { quickActionsFromHermesSuggestions, timestampMs } from './rpgWorkspaceSupport';

interface RpgHermesAssistSources {
  selectedLiveSessionId: string | null;
  selectedSessionSummary: RpgSessionSummaryPreview;
  quickActions: RpgQuickActionPreview[];
  latestCompletedTurnJobId: string | undefined;
  rpgJobs: JobRecord[];
  /** A Hermes sequence job was started, paused or canceled. */
  onJobChanged: () => Promise<void>;
}

/**
 * What the play screen offers next (the last turn's choices and suggestions, else Hermes's, else the scene's), and
 * Hermes's assist for developers: its suggestions, route decision, turn readout and sequence jobs.
 */
export function useRpgHermesAssist({
  selectedLiveSessionId,
  selectedSessionSummary,
  quickActions,
  latestCompletedTurnJobId,
  rpgJobs,
  onJobChanged,
}: RpgHermesAssistSources) {
  const hermesAssistMode = 'review_each_step';
  const hermesSuggestionsQuery = useQuery({
    queryKey: ['feature', 'rpg', 'hermes-suggestions', selectedLiveSessionId],
    queryFn: () => getHermesRpgSuggestions({ session_id: selectedLiveSessionId ?? '' }),
    enabled: Boolean(selectedLiveSessionId),
  });
  const hermesSuggestions = hermesSuggestionsQuery.data?.suggestions ?? [];
  const dynamicQuickActions = quickActionsFromHermesSuggestions(hermesSuggestions);
  // The last turn's (RQ-7.3): the answers to the game's question, else what the scene offers now.
  const turnOffers = useLatestRpgTurnOffers(selectedLiveSessionId ?? '');
  const offeredByTurn = (turnOffers?.choices.length ? turnOffers.choices : turnOffers?.suggestions ?? [])
    .map((row) => ({ label: row.label, command: row.command, icon: quickActionIcon(row.command) }));
  const responseOptions = offeredByTurn.length ? offeredByTurn
    : dynamicQuickActions.length ? dynamicQuickActions : quickActions;
  const hermesSequenceReviewRequest = buildHermesSequenceReviewRequest({
    assistMode: hermesAssistMode,
    quickActions: responseOptions,
    selectedSessionSummary,
    suggestions: hermesSuggestions,
  });
  const hermesSequenceReviewMutation = useMutation({
    mutationFn: () => checkHermesRpgSequence(hermesSequenceReviewRequest),
  });
  const hermesSequencePreview = hermesSequencePreviewModel(hermesSequenceReviewMutation.data);
  const hermesSuggestionState = selectedLiveSessionId
    ? rpgAssistStateFromItems(
      hermesSuggestions,
      hermesSuggestionsQuery.isPending,
      hermesSuggestionsQuery.isError || hermesSuggestionsQuery.data?.ok === false,
    )
    : 'idle';
  const hermesRouteDecisionQuery = useQuery({
    queryKey: ['feature', 'rpg', 'hermes-route-decision', 'rpg'],
    queryFn: () => getHermesRouteDecision('rpg'),
  });
  const hermesRouteDecision = hermesRouteDecisionQuery.data?.ok
    ? {
      mode: hermesRouteDecisionQuery.data.mode ?? 'rpg',
      hermesRole: hermesRouteDecisionQuery.data.role ?? 'suggest',
      owner: hermesRouteDecisionQuery.data.owner ?? 'rpg_sim',
      reviewRequired: Boolean(hermesRouteDecisionQuery.data.review_required),
      boundary: hermesRouteDecisionQuery.data.boundary ?? 'RPG simulation validates truth before state is accepted.',
    }
    : undefined;
  const hermesTurnReadoutQuery = useQuery({
    queryKey: ['feature', 'rpg', 'hermes-turn-readout', selectedLiveSessionId, latestCompletedTurnJobId],
    queryFn: () => readHermesRpgTurn({ session_id: selectedLiveSessionId ?? '' }),
    enabled: Boolean(selectedLiveSessionId),
  });
  const hermesTurnReadout = createRpgTurnReadoutPreview(hermesTurnReadoutQuery.data);
  const activeHermesSequenceJob = rpgJobs
    .filter((job) => job.type === 'rpg.hermes.sequence.execute')
    .sort((left, right) => timestampMs(right.created_at) - timestampMs(left.created_at))[0];
  const hermesSequenceJobMutation = useMutation({
    mutationFn: (action: 'start' | 'pause' | 'resume' | 'cancel') => {
      if (action === 'cancel' && activeHermesSequenceJob) {
        return omnixApiClient.cancelJob(activeHermesSequenceJob.id, 'Canceled from Hermes sequence job controls.');
      }
      return omnixApiClient.createJob({
        module: 'rpg',
        type: action === 'start' ? 'rpg.hermes.sequence.execute' : 'rpg.hermes.sequence.control',
        resource_class: 'cpu',
        priority: 0,
        input_ref: selectedLiveSessionId ? { session_id: selectedLiveSessionId } : null,
        input_payload: {
          action,
          sequence_id: hermesSequencePreview?.sequence_id,
          current_item_index: 0,
          item_count: hermesSequencePreview?.items?.length ?? 0,
          source: 'rpg-workspace',
        },
        stages: [
          { id: 'load-sequence', label: 'Load Hermes sequence state', resource_class: 'cpu', status: 'queued' },
          { id: 'execute-approved-step', label: 'Execute approved RPG step', resource_class: 'cpu', status: 'queued' },
          { id: 'persist-progress', label: 'Persist sequence progress', resource_class: 'cpu', status: 'queued' },
          { id: 'refresh-ui', label: 'Refresh RPG workspace', resource_class: 'cpu', status: 'queued' },
        ],
      });
    },
    onSuccess: onJobChanged,
  });
  return {
    activeHermesSequenceJob,
    hermesRouteDecision,
    hermesSequenceJobMutation,
    hermesSuggestionState,
    hermesSuggestions,
    hermesTurnReadout,
    responseOptions,
  };
}
