import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { listenerBackchannelsRolloutEnabled } from './live-voice-backchannel';
import {
  resetLiveVoiceHumanizationFlags,
  writeLiveVoiceHumanizationFlags,
} from './live-voice-humanization-flags';
import { shouldUseUnifiedLiveVoiceAudio } from './live-voice-unified-audio-controller';

beforeEach(() => {
  document.body.innerHTML = `
    <label class="assistant-voice-toggle">
      <input type="checkbox" checked>
    </label>`;
  resetLiveVoiceHumanizationFlags();
});

afterEach(() => {
  document.body.innerHTML = '';
  window.localStorage.clear();
});

describe('live voice humanization rollout integration', () => {
  it('master-disables unified humanized playback without changing Auto-speak state', () => {
    expect(shouldUseUnifiedLiveVoiceAudio('/api/chat/sessions/s1/messages/stream', { method: 'POST' })).toBe(true);

    writeLiveVoiceHumanizationFlags({ master: false });

    expect(shouldUseUnifiedLiveVoiceAudio('/api/chat/sessions/s1/messages/stream', { method: 'POST' })).toBe(false);
    expect(document.querySelector<HTMLInputElement>('.assistant-voice-toggle input')?.checked).toBe(true);
  });

  it('disables listener cues independently from response playback', () => {
    writeLiveVoiceHumanizationFlags({ listenerCues: false });

    expect(listenerBackchannelsRolloutEnabled()).toBe(false);
    expect(shouldUseUnifiedLiveVoiceAudio('/api/chat/sessions/s1/messages/stream', { method: 'POST' })).toBe(true);
  });
});
