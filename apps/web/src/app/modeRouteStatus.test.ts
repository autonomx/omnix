import { expect, test } from 'vitest';
import { getModeRouteStatusInfo } from './modeRouteStatus';

test('labels ready paths', () => {
  expect(getModeRouteStatusInfo('direct')).toMatchObject({ label: 'Direct provider', tone: 'ready' });
  expect(getModeRouteStatusInfo('live')).toMatchObject({ label: 'Live session', tone: 'ready' });
});

test('labels review paths', () => {
  expect(getModeRouteStatusInfo('adapter')).toMatchObject({ tone: 'review' });
  expect(getModeRouteStatusInfo('review')).toMatchObject({ label: 'Review required' });
});

test('labels runtime paths', () => {
  expect(getModeRouteStatusInfo('audio')).toMatchObject({ tone: 'runtime' });
  expect(getModeRouteStatusInfo('sim')).toMatchObject({ label: 'Simulation' });
});
