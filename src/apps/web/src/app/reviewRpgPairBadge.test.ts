import { expect, test } from 'vitest';
import { createReviewRpgPairBadge } from './reviewRpgPairBadge';
import { createReviewRpgPairStatus } from './reviewRpgPairStatus';

test('pair badge mirrors formatted waiting label', () => {
  const badge = createReviewRpgPairBadge(createReviewRpgPairStatus());

  expect(badge.text).toContain('Awaiting review context');
  expect(badge.ariaLabel).toContain(badge.text);
  expect(badge.readOnly).toBe(true);
  expect(badge.passive).toBe(true);
});

test('pair badge mirrors formatted ready label', () => {
  const badge = createReviewRpgPairBadge(createReviewRpgPairStatus({ reviewReady: true, rpgReady: true }));

  expect(badge.text).toContain('Review and RPG proposal ready');
  expect(badge.readOnly).toBe(true);
  expect(badge.passive).toBe(true);
});
