import { expect, test } from 'vitest';
import { createSidecarStatusState } from './sidecarStatusState';

test('sidecar status state starts idle', () => {
  expect(createSidecarStatusState()).toEqual({
    status: 'idle',
    message: 'Status not requested.',
    readOnly: true,
    executes: false,
  });
});

test('sidecar status state handles loading ready error and disabled', () => {
  expect(createSidecarStatusState({ loading: true })).toMatchObject({ status: 'loading', executes: false });
  expect(createSidecarStatusState({ payload: { ok: true, status: 'healthy' } })).toMatchObject({ status: 'ready', message: 'healthy' });
  expect(createSidecarStatusState({ error: 'Unavailable' })).toMatchObject({ status: 'error', message: 'Unavailable' });
  expect(createSidecarStatusState({ payload: { enabled: false } })).toMatchObject({ status: 'disabled', message: 'Service is disabled.' });
});
