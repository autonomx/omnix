import { expect, test } from 'vitest';
import { pairBadgeText } from './pairBadgeText';

test('pair badge text formats count and text', () => {
  expect(pairBadgeText(2, 'Ready')).toBe('2/2 Ready');
});
