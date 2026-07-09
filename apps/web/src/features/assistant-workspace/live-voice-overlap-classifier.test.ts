import { describe, expect, it } from 'vitest';

import {
  classifyOverlap,
  isLikelyEcho,
  shouldConfirmInterruption,
} from './live-voice-overlap-classifier';

describe('live voice overlap classifier', () => {
  it('confirms hard stops, corrections, questions, and sustained speech', () => {
    expect(classifyOverlap('stop').intent).toBe('hard_stop');
    expect(classifyOverlap('No, I meant the eastern road').intent).toBe('interrupt');
    expect(classifyOverlap('Where did you say the entrance was?').intent).toBe('interrupt');
    expect(shouldConfirmInterruption(classifyOverlap('I need to change the destination now'))).toBe(true);
  });

  it('keeps acknowledgements and noise non-authoritative', () => {
    expect(classifyOverlap('mhm').intent).toBe('backchannel');
    expect(classifyOverlap('yeah').intent).toBe('backchannel');
    expect(classifyOverlap('[cough]').intent).toBe('noise');
    expect(shouldConfirmInterruption(classifyOverlap('right'))).toBe(false);
  });

  it('recognizes likely assistant echo', () => {
    const assistant = 'The entrance is beneath the old watchtower near the river.';
    const echo = 'entrance beneath the old watchtower near the river';
    expect(isLikelyEcho(echo, assistant)).toBe(true);
    expect(classifyOverlap(echo, assistant).intent).toBe('noise');
  });
});
