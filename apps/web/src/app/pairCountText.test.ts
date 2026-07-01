import { expect, test } from 'vitest';
import { pairCountText } from './pairCountText';

test('pair count text formats count and text', () => {
  expect(pairCountText(2, 'Ready')).toBe('2/2 Ready');
});
