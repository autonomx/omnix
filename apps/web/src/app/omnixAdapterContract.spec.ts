import { expect, test } from 'vitest';
import { createAgentAdapterPlaceholder } from './omnixAdapterContract';

test('creates agent placeholder output', () => {
  const result = createAgentAdapterPlaceholder({ mode: 'agent', input: 'hello' });

  expect(result.ok).toBe(true);
  expect(result.mode).toBe('agent');
  expect(result.plan?.reviewRequired).toBe(true);
  expect(result.plan?.summary).toBe('hello');
});

test('rejects a different mode', () => {
  expect(createAgentAdapterPlaceholder({ mode: 'rpg', input: 'hello' }).ok).toBe(false);
});
