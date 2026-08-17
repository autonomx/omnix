import { describe, expect, it } from 'vitest';
import { createOmnixModePreview } from './omnixModePreview';

describe('createOmnixModePreview', () => {
  it('creates ready previews for existing paths', () => {
    expect(createOmnixModePreview('normal')).toMatchObject({
      label: 'Normal chat',
      path: 'direct',
      status: 'ready',
      statusLabel: 'Ready',
    });
    expect(createOmnixModePreview('live')).toMatchObject({
      label: 'Live chat',
      path: 'live',
      status: 'ready',
    });
  });

  it('creates review previews for gated lanes', () => {
    expect(createOmnixModePreview('agent')).toMatchObject({ path: 'adapter', status: 'review' });
    expect(createOmnixModePreview('house')).toMatchObject({ path: 'review', status: 'review' });
    expect(createOmnixModePreview('podcast')).toMatchObject({ path: 'audio', status: 'review' });
  });

  it('keeps rpg ready on the simulation path', () => {
    expect(createOmnixModePreview('rpg')).toMatchObject({ path: 'sim', owner: 'rpg_sim', status: 'ready' });
  });
});
