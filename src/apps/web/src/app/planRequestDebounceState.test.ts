import { expect, test } from 'vitest';
import { createPlanRequestDebounceState } from './planRequestDebounceState';

test('plan request debounce state blocks blank objectives', () => {
  expect(createPlanRequestDebounceState('   ', true)).toEqual({
    normalizedObjective: '',
    ready: false,
    reason: 'blank',
    autoStart: false,
  });
});

test('plan request debounce state waits until input is stable', () => {
  expect(createPlanRequestDebounceState(' Review step ', false)).toEqual({
    normalizedObjective: 'review step',
    ready: false,
    reason: 'waiting',
    autoStart: false,
  });
});

test('plan request debounce state becomes ready without auto start', () => {
  expect(createPlanRequestDebounceState(' Review step ', true)).toEqual({
    normalizedObjective: 'review step',
    ready: true,
    reason: 'ready',
    autoStart: false,
  });
});
