import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  fitVisemesToDuration,
  visemeAnimationFrameKeys,
  visemeSequenceFromText,
  type RuntimeAvatarPack,
} from './liveCharacterVisemeBridge';

const phasedPack: RuntimeAvatarPack = {
  render_mode: 'viseme',
  renderer: 'sprite',
  base_asset_id: 'image:maya-closed',
  mouth_frames: {
    closed: 'image:maya-closed',
    silence: 'image:maya-closed',
    A_35: 'image:maya-a-35',
    A_70: 'image:maya-a-70',
    A: 'image:maya-a',
    E_35: 'image:maya-e-35',
    E_70: 'image:maya-e-70',
    E: 'image:maya-e',
  },
};

afterEach(() => {
  window.dispatchEvent(new CustomEvent('omnix:character-avatar-runtime', { detail: null }));
  document.body.innerHTML = '';
});

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

  it('opens, changes, and closes through generated articulation phases', () => {
    expect(visemeAnimationFrameKeys(phasedPack, 'silence', 'A')).toEqual([
      'A_35',
      'A_70',
      'A',
    ]);
    expect(visemeAnimationFrameKeys(phasedPack, 'A', 'E')).toEqual([
      'A_35',
      'E_35',
      'E_70',
      'E',
    ]);
    expect(visemeAnimationFrameKeys(phasedPack, 'E', 'silence')).toEqual([
      'E_70',
      'E_35',
      'silence',
    ]);
  });

  it('prevents the four-frame envelope renderer from overwriting precise visemes', () => {
    window.dispatchEvent(new CustomEvent('omnix:character-avatar-runtime', {
      detail: { display_name: 'Maya', avatar_pack: phasedPack },
    }));
    const listener = vi.fn();
    window.addEventListener('omnix:character-avatar-frame', listener);

    window.dispatchEvent(new CustomEvent('omnix:character-avatar-frame', {
      detail: { frame: 'wide' },
    }));

    expect(listener).not.toHaveBeenCalled();
    window.removeEventListener('omnix:character-avatar-frame', listener);
  });
});
