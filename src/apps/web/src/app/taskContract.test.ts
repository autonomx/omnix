import { expect, test } from 'vitest';
import { makeTaskContract } from './taskContract';

test('marks agent for review', () => {
  expect(makeTaskContract('agent', 'x').review).toBe(true);
});

test('keeps normal without review', () => {
  expect(makeTaskContract('normal', 'x').review).toBe(false);
});
