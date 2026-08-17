import { expect, test } from 'vitest';
import { readModePlanStub } from './modePlanStub';

test('marks review flag', () => {
  expect(readModePlanStub('agent').reviewRequired).toBe(true);
  expect(readModePlanStub('normal').reviewRequired).toBe(false);
});
