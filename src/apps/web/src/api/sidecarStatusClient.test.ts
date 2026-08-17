import { expect, test } from 'vitest';
import {
  sidecarStatusPath,
  sidecarStatusQueryKey,
  sidecarStatusRefreshKey,
} from './sidecarStatusClient';

test('sidecar status path is stable and does not fetch by itself', () => {
  expect(sidecarStatusPath()).toBe('/api/sidecar/status');
});

test('sidecar status query key is stable', () => {
  expect(sidecarStatusQueryKey()).toEqual(['sidecar-status']);
});

test('sidecar status refresh key is deterministic and scoped', () => {
  expect(sidecarStatusRefreshKey()).toEqual(['sidecar-status', 'refresh', 'default']);
  expect(sidecarStatusRefreshKey(' panel ')).toEqual(['sidecar-status', 'refresh', 'panel']);
});
