import { describe, expect, it } from 'vitest';

import { voiceSectionSummary, type VoiceAsset } from './voiceAssets';

const asset = (metadata: Record<string, unknown>) => ({ id: 'voice-cloning:rudeus', metadata }) as unknown as VoiceAsset;

describe('the picked section on a voice card', () => {
  it('names the section and how its test takes went', () => {
    const summary = voiceSectionSummary(asset({
      section_choice: {
        sample_seconds: 17.8,
        chosen: { start: 4.0, end: 10.75, silent: 1, takes: 12 },
        candidates: [{}, {}, {}],
      },
    }));

    expect(summary).toEqual({
      label: 'best 6.8 s section',
      title: 'Picked from 3 sections of 17.8 s: 1 of 12 test takes went silent.',
    });
  });

  it('says so when the whole sample tested best', () => {
    const summary = voiceSectionSummary(asset({
      section_choice: { sample_seconds: 12.0, chosen: { start: 0, end: 12, silent: 0, takes: 12, whole: true }, candidates: [{}, {}] },
    }));

    expect(summary?.label).toBe('whole sample tested best');
  });

  it('shows nothing when no section was picked', () => {
    expect(voiceSectionSummary(asset({}))).toBeNull();
    expect(voiceSectionSummary(asset({ section_choice: { skipped: 'short' } }))).toBeNull();
  });
});
