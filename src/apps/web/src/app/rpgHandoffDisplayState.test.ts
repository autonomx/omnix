import { expect, test } from 'vitest';
import { createRpgHandoffDisplayState } from './rpgHandoffDisplayState';

test('rpg handoff display state marks proposal as not applied', () => {
  expect(
    createRpgHandoffDisplayState({
      command_text: 'inspect the door',
      simulation_must_validate: true,
      review_required: true,
    }),
  ).toEqual({
    title: 'Proposed RPG handoff — not applied',
    commandText: 'inspect the door',
    applied: false,
    simulationMustValidate: true,
    reviewRequired: true,
    executes: false,
  });
});

test('rpg handoff display state handles missing payload safely', () => {
  expect(createRpgHandoffDisplayState()).toMatchObject({
    commandText: '',
    applied: false,
    reviewRequired: true,
    executes: false,
  });
});
