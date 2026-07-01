import { expect, test } from 'vitest';
import { createRiskListState, createStepListState } from './stepsRisksDisplayState';

test('steps and risks display state handles empty values', () => {
  expect(createStepListState(undefined)).toEqual([]);
  expect(createRiskListState(undefined)).toEqual([]);
});

test('steps and risks display state skips malformed list entries', () => {
  expect(createStepListState(['bad', null])).toEqual([]);
  expect(createRiskListState(['bad', null])).toEqual([]);
});

test('steps and risks display state maps normal lists to review items', () => {
  expect(createStepListState([{ id: 's1', title: 'Read', description: 'Inspect.', status: 'ready' }])).toEqual([
    {
      id: 's1',
      title: 'Read',
      detail: 'Inspect.',
      badge: 'ready',
      reviewRequired: true,
    },
  ]);
  expect(createRiskListState([{ id: 'r1', label: 'Boundary', message: 'Do not apply.', severity: 'high' }])).toEqual([
    {
      id: 'r1',
      title: 'Boundary',
      detail: 'Do not apply.',
      badge: 'high',
      reviewRequired: true,
    },
  ]);
});
