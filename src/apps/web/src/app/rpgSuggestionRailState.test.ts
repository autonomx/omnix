import { expect, test } from 'vitest';
import { createRpgCommandSuggestion } from './rpgCommandSuggestion';
import { createRpgSuggestionRailState } from './rpgSuggestionRailState';

test('rpg suggestion rail stays hidden when empty', () => {
  expect(createRpgSuggestionRailState()).toEqual({
    visible: false,
    suggestions: [],
    fillsCommandOnly: true,
    submits: false,
    executes: false,
  });
});

test('rpg suggestion rail exposes planner suggestions without submit behavior', () => {
  const suggestion = createRpgCommandSuggestion({ title: 'Inspect' });

  expect(createRpgSuggestionRailState([suggestion])).toEqual({
    visible: true,
    suggestions: [suggestion],
    fillsCommandOnly: true,
    submits: false,
    executes: false,
  });
});
