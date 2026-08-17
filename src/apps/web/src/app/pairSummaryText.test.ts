import { expect, test } from 'vitest';
import { pairSummaryText } from './pairSummaryText';

test('pair summary text uses count and text', () => {
  expect(pairSummaryText({ text: 'Ready', visibleCount: 2, readOnly: true })).toBe('2/2 Ready');
});
