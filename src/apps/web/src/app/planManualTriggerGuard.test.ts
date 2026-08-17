import { expect, test } from 'vitest';
import { createPlanManualTriggerGuard } from './planManualTriggerGuard';

test('manual trigger guard does not start from default helper state', () => {
  expect(createPlanManualTriggerGuard()).toEqual({
    canStart: false,
    reason: 'not_ready',
    autoStart: false,
  });
});

test('manual trigger guard blocks ready state without explicit user action', () => {
  expect(createPlanManualTriggerGuard({ ready: true })).toEqual({
    canStart: false,
    reason: 'manual_required',
    autoStart: false,
  });
});

test('manual trigger guard allows only explicit manual trigger', () => {
  expect(createPlanManualTriggerGuard({ ready: true, manualTrigger: true })).toEqual({
    canStart: true,
    reason: 'ready',
    autoStart: false,
  });
});
