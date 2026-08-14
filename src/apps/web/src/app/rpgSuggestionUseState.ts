import type { RpgCommandSuggestion } from './rpgCommandSuggestion';

export interface RpgSuggestionUseState {
  commandText: string;
  fillsCommand: true;
  submits: false;
  executes: false;
}

export function useRpgSuggestionText(suggestion: RpgCommandSuggestion): RpgSuggestionUseState {
  return {
    commandText: suggestion.commandText,
    fillsCommand: true,
    submits: false,
    executes: false,
  };
}
