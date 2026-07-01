import { expect, test } from 'vitest';
import { createRpgCommandSuggestion } from './rpgCommandSuggestion';
import { useRpgSuggestionText } from './rpgSuggestionUseState';

test('using rpg planner suggestion only fills command text', () => {
  const suggestion = createRpgCommandSuggestion({ title: 'Inspect', description: 'Check the door.' });

  expect(useRpgSuggestionText(suggestion)).toEqual({
    commandText: 'Inspect: Check the door.',
    fillsCommand: true,
    submits: false,
    executes: false,
  });
});
