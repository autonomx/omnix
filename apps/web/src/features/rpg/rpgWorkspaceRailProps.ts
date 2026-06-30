import { rpgAssistStateFromItems, type RpgAssistItemPreview, type RpgAssistState } from './rpgAssistState';
import { createRpgRailModeState } from './rpgRailModeState';
import { createRpgTurnReadoutPreview } from './rpgTurnReadoutState';

export interface RpgWorkspaceRailPropsInput {
  enabled: boolean;
  suggestions?: RpgAssistItemPreview[];
  suggestionsPending?: boolean;
  suggestionsFailed?: boolean;
  modePayload?: Record<string, unknown>;
  modePending?: boolean;
  modeFailed?: boolean;
  readoutPayload?: Parameters<typeof createRpgTurnReadoutPreview>[0];
  readoutPending?: boolean;
  readoutFailed?: boolean;
}

export interface RpgWorkspaceRailQueryFlags {
  isPending?: boolean;
  isError?: boolean;
}

export function failedRpgWorkspaceRailPayload(payload: { ok?: boolean } | undefined, flags: RpgWorkspaceRailQueryFlags): boolean {
  return Boolean(flags.isError || payload?.ok === false);
}

export function createRpgWorkspaceRailProps(input: RpgWorkspaceRailPropsInput) {
  const suggestions = input.suggestions ?? [];
  const suggestionState: RpgAssistState = input.enabled
    ? rpgAssistStateFromItems(suggestions, Boolean(input.suggestionsPending), Boolean(input.suggestionsFailed))
    : 'idle';
  const routeDecision = createRpgRailModeState(input.modePayload);
  const routeDecisionState: RpgAssistState = input.modePending
    ? 'loading'
    : input.modeFailed
      ? 'error'
      : routeDecision
        ? 'ready'
        : 'empty';
  const turnReadout = createRpgTurnReadoutPreview(input.readoutPayload);
  const turnReadoutState: RpgAssistState = !input.enabled
    ? 'idle'
    : input.readoutPending
      ? 'loading'
      : input.readoutFailed
        ? 'error'
        : turnReadout
          ? 'ready'
          : 'empty';

  return {
    hermesRouteDecision: routeDecision
      ? {
        mode: routeDecision.mode,
        hermesRole: routeDecision.role,
        owner: routeDecision.owner,
        reviewRequired: routeDecision.reviewRequired,
        boundary: routeDecision.boundary,
      }
      : undefined,
    hermesRouteDecisionState: routeDecisionState,
    hermesSuggestionState: suggestionState,
    hermesSuggestions: suggestions,
    hermesTurnReadout: turnReadout,
    hermesTurnReadoutState: turnReadoutState,
  };
}
