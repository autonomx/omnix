import { expect, test } from 'vitest';
import { createReviewRpgPairStatus } from './reviewRpgPairStatus';

test('review rpg pair status defaults to passive waiting state', () => {
  expect(createReviewRpgPairStatus()).toEqual({
    reviewVisible: false,
    rpgVisible: false,
    label: 'Awaiting review context',
    hasControls: false,
    submits: false,
    executes: false,
  });
});

test('review rpg pair status marks both panels ready without controls', () => {
  expect(createReviewRpgPairStatus({ reviewReady: true, rpgReady: true })).toEqual({
    reviewVisible: true,
    rpgVisible: true,
    label: 'Review and RPG proposal ready',
    hasControls: false,
    submits: false,
    executes: false,
  });
});
