import { expect, test } from 'vitest';
import { createRpgCommandSuggestion } from './rpgCommandSuggestion';

test('rpg command suggestion adapts plan step to text only', () => {
  expect(createRpgCommandSuggestion({ title: 'Inspect', description: 'Check the locked door.' })).toEqual({
    commandText: 'Inspect: Check the locked door.',
    submits: false,
    executes: false,
  });
});

test('rpg command suggestion handles missing description safely', () => {
  expect(createRpgCommandSuggestion({ title: 'Wait' })).toEqual({
    commandText: 'Wait',
    submits: false,
    executes: false,
  });
});
