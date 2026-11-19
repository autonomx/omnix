import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ASSISTANT_AUDIO_DUCK_EVENT, ASSISTANT_VOICE_INTERRUPT_EVENT } from '../../../events/bus';
import { liveConversationStore } from './live-conversation-store';
import type { LiveVoiceSession } from './live-voice-controller-state';
import { updateLiveConversationSettings } from './live-voice-conversation-settings';
import { initializeLiveVoicePendingOutputInterrupt } from './live-voice-pending-output-interrupt';
import { assessOverlapCandidate, settleDeferredInterrupt, SPEAKER_PENDING_GAIN, SPEAKER_PENDING_UNDUCK_MS } from './live-voice-preview';
import { liveSpeakerScores } from './live-voice-speaker-gate';

let interrupts: unknown[];
let gains: number[];
const countInterrupt = (event: Event) => { interrupts.push((event as CustomEvent).detail); };
const recordGain = (event: Event) => { gains.push((event as CustomEvent<{ gain: number }>).detail.gain); };

function overlapSession(partialTranscript: string): LiveVoiceSession {
  return {
    card: document.createElement('section'),
    partialTranscript,
    overlapIntent: null,
    interruptionDispatched: false,
    deferredInterrupt: null,
    reporter: { record: vi.fn() },
  } as unknown as LiveVoiceSession;
}

function onlyRespondToMe(on: boolean): void {
  updateLiveConversationSettings({ onlyRespondToMe: on });
  liveSpeakerScores.setAvailable(true);
}

beforeEach(() => {
  interrupts = [];
  gains = [];
  window.localStorage.clear();
  liveSpeakerScores.reset();
  window.addEventListener(ASSISTANT_VOICE_INTERRUPT_EVENT, countInterrupt);
  window.addEventListener(ASSISTANT_AUDIO_DUCK_EVENT, recordGain);
});

afterEach(() => {
  vi.useRealTimers();
  window.removeEventListener(ASSISTANT_VOICE_INTERRUPT_EVENT, countInterrupt);
  window.removeEventListener(ASSISTANT_AUDIO_DUCK_EVENT, recordGain);
  liveSpeakerScores.reset();
  window.localStorage.clear();
});

describe('speech over a reply with "Only respond to me" on', () => {
  it('ducks the reply instead of stopping it, until the final says whose voice it was', () => {
    onlyRespondToMe(true);
    const session = overlapSession('stop');

    assessOverlapCandidate(session);
    assessOverlapCandidate(session);

    expect(interrupts).toEqual([]);
    expect(gains).toEqual([SPEAKER_PENDING_GAIN]);
    expect(session.interruptionDispatched).toBe(true);
    expect(session.deferredInterrupt).toMatchObject({ intent: 'hard_stop' });

    expect(settleDeferredInterrupt(session, true, true)).toBe(true);
    expect(interrupts).toEqual([expect.objectContaining({ intent: 'hard_stop' })]);
    expect(gains.at(-1)).toBe(1);
    expect(session.deferredInterrupt).toBeNull();
  });

  it('lets the reply play on in another voice, or once it has ended', () => {
    onlyRespondToMe(true);
    const other = overlapSession('stop');
    assessOverlapCandidate(other);
    expect(settleDeferredInterrupt(other, false, true)).toBe(false);

    const finished = overlapSession('stop');
    assessOverlapCandidate(finished);
    expect(settleDeferredInterrupt(finished, true, false)).toBe(false);

    expect(interrupts).toEqual([]);
    expect(gains).toEqual([SPEAKER_PENDING_GAIN, 1, SPEAKER_PENDING_GAIN, 1]);
  });

  it('stops ducking a reply whose final never comes', () => {
    vi.useFakeTimers();
    onlyRespondToMe(true);
    const session = overlapSession('stop');
    assessOverlapCandidate(session);

    vi.advanceTimersByTime(SPEAKER_PENDING_UNDUCK_MS);

    expect(gains).toEqual([SPEAKER_PENDING_GAIN, 1]);
    expect(session.deferredInterrupt).not.toBeNull();
  });

  it('stops the reply at once when the setting is off', () => {
    onlyRespondToMe(false);
    const session = overlapSession('stop');

    assessOverlapCandidate(session);

    expect(interrupts).toEqual([expect.objectContaining({ intent: 'hard_stop' })]);
    expect(gains).not.toContain(SPEAKER_PENDING_GAIN);
    expect(session.deferredInterrupt).toBeNull();
  });
});

describe('speech before a reply is audible with "Only respond to me" on', () => {
  it('does not cancel the reply: the final decides', () => {
    onlyRespondToMe(true);
    liveConversationStore.dispatch({ type: 'reset_all' });
    liveConversationStore.dispatch({ type: 'conversation', event: { type: 'connection', value: 'connected' } });
    liveConversationStore.dispatch({ type: 'conversation', event: { type: 'assistant_turn', value: 'generating' } });
    const cleanup = initializeLiveVoicePendingOutputInterrupt();

    window.dispatchEvent(new CustomEvent('omnix:assistant-live-voice-user-speech', { detail: {} }));

    expect(interrupts).toEqual([]);
    cleanup();
    liveConversationStore.dispatch({ type: 'reset_all' });
  });
});
