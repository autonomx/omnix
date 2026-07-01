import { expect, test } from 'vitest';
import { modeMetadataPath } from './modeMetadataClient';

test('builds all mode metadata path', () => {
  expect(modeMetadataPath()).toBe('/api/modes/metadata');
});

test('builds mapped mode metadata paths', () => {
  expect(modeMetadataPath('normal')).toBe('/api/modes/metadata?mode=normal_chat');
  expect(modeMetadataPath('agent')).toBe('/api/modes/metadata?mode=agent_mode');
  expect(modeMetadataPath('rpg')).toBe('/api/modes/metadata?mode=rpg');
});
