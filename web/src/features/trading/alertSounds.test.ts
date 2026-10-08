import { afterEach, describe, expect, it, vi } from 'vitest';
import { alertSoundName, playAlertSound, resetAlertSounds } from './alertSounds';

function fakeAudio() {
  const started: number[] = [];
  const param = () => ({ value: 0, setValueAtTime: vi.fn(), exponentialRampToValueAtTime: vi.fn() });
  return {
    started,
    audio: {
      currentTime: 10,
      destination: {},
      state: 'running',
      resume: vi.fn(async () => undefined),
      createOscillator: () => ({ frequency: param(), connect: vi.fn(), start: (at: number) => started.push(at), stop: vi.fn() }),
      createGain: () => ({ gain: param(), connect: vi.fn() }),
    },
  };
}

afterEach(() => resetAlertSounds());

describe('alert sounds', () => {
  it('plays the chosen sound, the chime by default', () => {
    const { audio, started } = fakeAudio();
    expect(playAlertSound(undefined, () => audio as never)).toBe(true);
    expect(started).toEqual([10, 10.16]);
    expect(alertSoundName('alarm')).toBe('alarm');
    expect(alertSoundName('siren')).toBe('chime');
  });

  it('reports a browser without audio instead of throwing', () => {
    expect(playAlertSound('beep', () => null)).toBe(false);
    resetAlertSounds();
    expect(playAlertSound('beep', () => { throw new Error('blocked'); })).toBe(false);
  });
});
