import { expect, test } from 'vitest';
import { createReviewRpgPairStatus } from './reviewRpgPairStatus';

test('review rpg pair status defaults to passive waiting state', () => {
  expect(createReviewRpgPairStatus()).toEqual({
    reviewVisible: false,
    rpgVisible: false,
    label: 'Awaiting review context',
    readOnly: true,
    passive: true,
  });
});

test('review rpg pair status marks both panels ready as read only', () => {
  expect(createReviewRpgPairStatus({ reviewReady: true, rpgReady: true })).toEqual({
    reviewVisible: true,
    rpgVisible: true,
    label: 'Review and RPG proposal ready',
    readOnly: true,
    passive: true,
  });
});
