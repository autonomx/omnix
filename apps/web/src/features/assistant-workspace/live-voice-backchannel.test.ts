import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  decideBackchannel,
  requestEphemeralBackchannel,
  resolveBackchannelTranscript,
} from './live-voice-backchannel';

describe('ephemeral live voice acknowledgements', () => {
  beforeEach(() => {
    window.localStorage.clear();
    document.body.innerHTML = '';
  });

  it('is opt-in and blocks sensitive or semantic speech', () => {
    expect(decideBackchannel('mhm', 'off', 10_000, 0).allowed).toBe(false);
    expect(decideBackchannel('my passcode is 123456', 'natural', 10_000, 0).reason).toBe('sensitive_dictation');
    expect(decideBackchannel('No, that is wrong', 'natural', 10_000, 0).reason).toBe('semantic_turn');
    expect(decideBackchannel('Where is the gate?', 'natural', 10_000, 0).reason).toBe('semantic_turn');
  });

  it('uses fixed non-authoritative tokens and enforces cooldown', () => {
    const allowed = decideBackchannel('yeah', 'minimal', 10_000, 0);
    expect(allowed).toEqual({ allowed: true, token: 'mhm', reason: 'minimal' });
    expect(decideBackchannel('mhm', 'natural', 12_000, 10_000).reason).toBe('cooldown');
  });

  it('dispatches an ephemeral event without creating a chat message', () => {
    window.localStorage.setItem('omnix.chatbot.assistantSettings', JSON.stringify({ backchannelMode: 'minimal' }));
    const listener = vi.fn();
    window.addEventListener('omnix:assistant-backchannel', listener);

    expect(requestEphemeralBackchannel('mhm', 'minimal')).toBe(true);
    expect(listener).toHaveBeenCalledTimes(1);
    expect((listener.mock.calls[0]?.[0] as CustomEvent).detail).toEqual({ token: 'mhm', expiresAfterMs: 900 });
    expect(document.querySelector('.assistant-chat-message')).toBeNull();
  });

  it('recovers the classified acknowledgement from the current draft row', () => {
    document.body.innerHTML = `
      <div class="assistant-voice-transcript">
        <p data-live-voice-id="live-voice-draft"><span><strong>You</strong></span>mhm</p>
      </div>`;

    expect(resolveBackchannelTranscript(undefined)).toBe('mhm');
    expect(resolveBackchannelTranscript('yeah')).toBe('yeah');
  });
});
