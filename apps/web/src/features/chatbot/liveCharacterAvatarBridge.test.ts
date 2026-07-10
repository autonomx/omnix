import { describe, expect, it } from 'vitest';
import { characterAvatarAssetUrl, mouthFrameForRms, pcmMouthTimeline } from './liveCharacterAvatarBridge';

describe('live character avatar audio envelope', () => {
  it('maps RMS levels to four stable mouth states', () => {
    expect(mouthFrameForRms(0)).toBe('closed');
    expect(mouthFrameForRms(0.02)).toBe('small');
    expect(mouthFrameForRms(0.05)).toBe('medium');
    expect(mouthFrameForRms(0.2)).toBe('wide');
  });

  it('produces a compact timeline and browser-safe asset URL', () => {
    const samples = new Int16Array(4800);
    samples.fill(0, 0, 1200);
    samples.fill(4000, 1200, 2400);
    samples.fill(14000, 2400, 3600);
    samples.fill(0, 3600);
    const timeline = pcmMouthTimeline(samples, 24_000, 50);
    expect(timeline[0]).toEqual({ offsetMs: 0, frame: 'closed' });
    expect(timeline.some((point) => point.frame === 'wide')).toBe(true);
    expect(characterAvatarAssetUrl('image:maya closed')).toBe('/api/assets/image%3Amaya%20closed/file');
  });
});
