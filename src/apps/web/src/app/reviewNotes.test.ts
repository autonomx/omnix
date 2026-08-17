import { expect, test } from 'vitest';
import { normalizeReviewNotes } from './reviewNotes';

test('review notes normalizes whitespace and trimming', () => {
  expect(normalizeReviewNotes('  Looks   safe.\nNeeds review.  ')).toBe('Looks safe. Needs review.');
});

test('review notes truncates to max length', () => {
  expect(normalizeReviewNotes('abcdef', 4)).toBe('abcd');
});

test('review notes handles empty values', () => {
  expect(normalizeReviewNotes('   ')).toBe('');
});
