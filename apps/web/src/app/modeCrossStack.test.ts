import { expect, test } from 'vitest';
import { createOmnixModePreview } from './omnixModePreview';
import { toBackendModeId } from './modeNameMap';

test('mode names align with preview paths', () => {
  expect(toBackendModeId('normal')).toBe('normal_chat');
  expect(createOmnixModePreview('normal').path).toBe('direct');
  expect(toBackendModeId('agent')).toBe('agent_mode');
  expect(createOmnixModePreview('agent').path).toBe('adapter');
  expect(toBackendModeId('rpg')).toBe('rpg');
  expect(createOmnixModePreview('rpg').path).toBe('sim');
});
