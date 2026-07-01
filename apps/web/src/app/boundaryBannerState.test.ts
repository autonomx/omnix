import { expect, test } from 'vitest';
import { createBoundaryBannerState } from './boundaryBannerState';

test('boundary banner displays RPG simulation ownership', () => {
  expect(createBoundaryBannerState('rpg')).toEqual({
    visible: true,
    title: 'Proposal only',
    message: 'RPG simulation validates truth before any state changes.',
    proposalOnly: true,
    simulationValidates: true,
  });
});

test('boundary banner stays hidden for non-RPG mode defaults', () => {
  expect(createBoundaryBannerState('normal')).toEqual({
    visible: false,
    title: '',
    message: '',
    proposalOnly: true,
    simulationValidates: false,
  });
});
