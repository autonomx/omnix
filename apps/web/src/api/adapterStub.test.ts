import { expect, test } from 'vitest';
import { readAgentAdapterStub } from './agentAdapterClient';

test('returns gated result', () => {
  const result = readAgentAdapterStub({ input: 'x' });

  expect(result.ok).toBe(true);
  expect(result.plan?.reviewRequired).toBe(true);
});
