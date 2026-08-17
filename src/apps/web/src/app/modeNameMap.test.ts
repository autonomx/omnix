import { expect, test } from 'vitest';
import { toBackendModeId, toFrontendModeId } from './modeNameMap';

test('maps frontend mode ids to backend ids', () => {
  expect(toBackendModeId('normal')).toBe('normal_chat');
  expect(toBackendModeId('live')).toBe('live_chat');
  expect(toBackendModeId('agent')).toBe('agent_mode');
  expect(toBackendModeId('house')).toBe('house_ai');
  expect(toBackendModeId('podcast')).toBe('podcast');
  expect(toBackendModeId('rpg')).toBe('rpg');
});

test('maps backend mode ids to frontend ids', () => {
  expect(toFrontendModeId('normal_chat')).toBe('normal');
  expect(toFrontendModeId('live_chat')).toBe('live');
  expect(toFrontendModeId('agent_mode')).toBe('agent');
  expect(toFrontendModeId('house_ai')).toBe('house');
  expect(toFrontendModeId('podcast')).toBe('podcast');
  expect(toFrontendModeId('rpg')).toBe('rpg');
});
