import { expect, test } from 'vitest';
import { createPairBadgeSummary } from './pairBadgeSummary';

test('pair badge summary counts no visible panels', () => {
  expect(createPairBadgeSummary({ text: 'Waiting' })).toEqual({
    text: 'Waiting',
    visibleCount: 0,
    readOnly: true,
  });
});

test('pair badge summary counts visible panels', () => {
  expect(createPairBadgeSummary({ text: 'Ready', reviewVisible: true, rpgVisible: true })).toEqual({
    text: 'Ready',
    visibleCount: 2,
    readOnly: true,
  });
});
