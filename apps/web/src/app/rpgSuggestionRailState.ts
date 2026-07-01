import type { RpgCommandSuggestion } from './rpgCommandSuggestion';

export interface RpgSuggestionRailState {
  visible: boolean;
  suggestions: RpgCommandSuggestion[];
  fillsCommandOnly: true;
  submits: false;
  executes: false;
}

export function createRpgSuggestionRailState(
  suggestions: RpgCommandSuggestion[] = [],
): RpgSuggestionRailState {
  return {
    visible: suggestions.length > 0,
    suggestions,
    fillsCommandOnly: true,
    submits: false,
    executes: false,
  };
}
