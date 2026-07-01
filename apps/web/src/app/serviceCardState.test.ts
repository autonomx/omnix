import { expect, test } from 'vitest';
import { createServiceCardState } from './serviceCardState';

test('creates service card state', () => {
  expect(createServiceCardState('Service', 'ready')).toEqual({ label: 'Service', status: 'ready' });
});
