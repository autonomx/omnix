import { expect, test } from 'vitest';
import { createReviewChecklistState } from './reviewChecklistState';

test('review checklist defaults to not user-reviewed and non-executing', () => {
  expect(createReviewChecklistState('rpg')).toEqual([
    { id: 'user-reviewed', label: 'User reviewed proposal', checked: false },
    { id: 'no-execution', label: 'No execution performed', checked: true },
    { id: 'simulation-validation', label: 'Simulation validation required for RPG', checked: true },
    { id: 'risks-visible', label: 'Risks visible before use', checked: true },
  ]);
});

test('review checklist can mark user reviewed without enabling execution', () => {
  const checklist = createReviewChecklistState('normal', true);

  expect(checklist[0]).toEqual({ id: 'user-reviewed', label: 'User reviewed proposal', checked: true });
  expect(checklist[1]).toEqual({ id: 'no-execution', label: 'No execution performed', checked: true });
  expect(checklist[2]).toEqual({ id: 'simulation-validation', label: 'Simulation validation required for RPG', checked: false });
});
