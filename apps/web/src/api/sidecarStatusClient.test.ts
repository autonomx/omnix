import { expect, test } from 'vitest';
import { sidecarStatusPath, sidecarStatusQueryKey } from './sidecarStatusClient';

test('sidecar status path is stable and does not fetch by itself', () => {
  expect(sidecarStatusPath()).toBe('/api/sidecar/status');
});

test('sidecar status query key is stable', () => {
  expect(sidecarStatusQueryKey()).toEqual(['sidecar-status']);
});
