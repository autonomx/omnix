import { describe, expect, it } from 'vitest';
import { fitVisemesToDuration, visemeSequenceFromText } from './liveCharacterVisemeBridge';

describe('live character timed visemes', () => {
  it('maps text into distinct visual mouth groups', () => {
    const sequence = visemeSequenceFromText('Maya loves five blue owls.');
    expect(sequence[0]).toBe('MBP');
    expect(sequence).toContain('A');
    expect(sequence).toContain('FV');
    expect(sequence).toContain('L');
    expect(sequence).toContain('O');
    expect(sequence).toContain('U');
    expect(sequence.at(-1)).toBe('silence');
  });

  it('fits cues to the actual streamed audio duration', () => {
    const cues = fitVisemesToDuration('Hello Maya', 1_250);
    expect(cues[0].startMs).toBe(0);
    const finalCue = cues.at(-1);
    expect(finalCue).toBeDefined();
    expect((finalCue?.startMs ?? 0) + (finalCue?.durationMs ?? 0)).toBeCloseTo(1_250, 5);
    expect(cues.every((cue) => cue.durationMs > 0)).toBe(true);
  });

  it('uses one bounded silence cue when no text is available', () => {
    expect(fitVisemesToDuration('', 400)).toEqual([
      { viseme: 'silence', startMs: 0, durationMs: 400 },
    ]);
  });
});
