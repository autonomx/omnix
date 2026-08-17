import { expect, test } from 'vitest';
import { formatReviewRpgPairLabel } from './reviewRpgPairLabel';
import { createReviewRpgPairStatus } from './reviewRpgPairStatus';

test('pair label formats waiting state', () => {
  expect(formatReviewRpgPairLabel(createReviewRpgPairStatus())).toContain('read-only');
});

test('pair label formats ready state', () => {
  expect(formatReviewRpgPairLabel(createReviewRpgPairStatus({ reviewReady: true, rpgReady: true }))).toContain(
    'Review and RPG proposal ready',
  );
});
