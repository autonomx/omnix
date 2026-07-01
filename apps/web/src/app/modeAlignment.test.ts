import { expect, test } from 'vitest';
import { createOmnixModePreview } from './omnixModePreview';
import { toBackendModeId } from './modeNameMap';

test('mode names align for stable lanes', () => {
  expect(toBackendModeId('normal')).toBe('normal_chat');
  expect(createOmnixModePreview('normal').path).toBe('direct');
  expect(toBackendModeId('rpg')).toBe('rpg');
  expect(createOmnixModePreview('rpg').path).toBe('sim');
});
