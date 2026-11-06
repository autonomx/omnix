import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ASSISTANT_AUDIO_PLAYBACK_STATE_EVENT, emitOmnixEvent } from '../../../events/bus';
import { liveConversationProfileClient, type LiveConversationProfile } from '../chat/liveConversationProfileClient';
import { initializeLiveConversationStoreBridge } from './live-conversation-store-bridge';
import { liveConversationStore } from './live-conversation-store';

vi.mock('../chat/liveConversationProfileClient', async (importOriginal) => {
  const original = await importOriginal<typeof import('../chat/liveConversationProfileClient')>();
  // A session's profile load never settles unless a test resolves it.
  return { ...original, liveConversationProfileClient: { ...original.liveConversationProfileClient,
    get: vi.fn(() => new Promise(() => undefined)) } };
});

let dispose: (() => void) | null = null;

beforeEach(() => {
  window.localStorage.clear();
  liveConversationStore.reset();
  dispose = initializeLiveConversationStoreBridge();
});

afterEach(() => {
  dispose?.();
  dispose = null;
  liveConversationStore.reset();
});

describe('live conversation store bridge', () => {
  it('projects React chat selection before the session fetch bridge completes', () => {
    window.dispatchEvent(new CustomEvent('omnix:chat-session-selected', {
      detail: { sessionId: 'chat:new-call' },
    }));

    expect(liveConversationStore.getState().sessionId).toBe('chat:new-call');
  });

  it('keeps the floor with a reply still playing after a final, and frees it otherwise', () => {
    // Real: one ignored noise left the floor unclaimed, and the rest of the reply had no overlap protection.
    const final = () => window.dispatchEvent(new CustomEvent('omnix:assistant-voice-perf', {
      detail: { stage: 'stt_final_received', transcript: '' },
    }));
    const playback = (speaking: boolean) => window.dispatchEvent(new CustomEvent(ASSISTANT_AUDIO_PLAYBACK_STATE_EVENT, {
      detail: { speaking },
    }));

    playback(true);
    final();
    expect(liveConversationStore.getState().conversation.floorOwner).toBe('assistant');

    playback(false);
    final();
    expect(liveConversationStore.getState().conversation.floorOwner).toBe('unclaimed');
  });

  it('takes the chat session selected before the bridge was installed', () => {
    dispose?.();
    liveConversationStore.reset();
    emitOmnixEvent('omnix:chat-session-selected', { sessionId: 'chat:early', session: undefined });
    dispose = initializeLiveConversationStoreBridge();

    expect(liveConversationStore.getState().sessionId).toBe('chat:early');
    emitOmnixEvent('omnix:chat-session-selected', { sessionId: null, session: undefined });
  });

  it('projects call, speech, transcript, playback, and interruption events', () => {
    window.dispatchEvent(new CustomEvent('omnix:live-chat-session-changed', {
      detail: { sessionId: 'chat:one', characterId: 'maya', characterName: 'Maya', profileVersion: 3 },
    }));
    window.dispatchEvent(new CustomEvent('omnix:assistant-live-voice-call-start'));
    expect(liveConversationStore.getState().conversation.connection).toBe('connecting');

    window.dispatchEvent(new CustomEvent('omnix:assistant-live-voice-call-connected'));
    expect(liveConversationStore.getState().conversation.connection).toBe('connected');

    window.dispatchEvent(new CustomEvent('omnix:assistant-live-voice-user-speech', {
      detail: { partialTranscript: 'Wait, I meant' },
    }));
    expect(liveConversationStore.getState()).toMatchObject({
      sessionId: 'chat:one',
      identity: { characterId: 'maya', displayName: 'Maya', profileVersion: 3 },
      transcript: { partial: 'Wait, I meant' },
      conversation: { userTurn: 'speaking', floorOwner: 'user' },
    });

    window.dispatchEvent(new CustomEvent('omnix:assistant-voice-perf', {
      detail: { stage: 'stt_final_received', transcript: 'Wait, I meant Friday.' },
    }));
    expect(liveConversationStore.getState().transcript).toMatchObject({
      partial: '', lastFinal: 'Wait, I meant Friday.', recentFinals: ['Wait, I meant Friday.'],
    });

    window.dispatchEvent(new CustomEvent('omnix:assistant-audio-playback-state', { detail: { speaking: true } }));
    expect(liveConversationStore.getState().conversation).toMatchObject({
      assistantTurn: 'speaking', delivery: 'audio_started', floorOwner: 'assistant',
    });

    window.dispatchEvent(new CustomEvent('omnix:assistant-voice-interrupt'));
    expect(liveConversationStore.getState().conversation).toMatchObject({
      assistantTurn: 'interrupted', delivery: 'interrupted', bargeIn: 'accepted', floorOwner: 'user',
    });
  });

  it('keeps speech over assistant playback as a candidate until classification', () => {
    window.dispatchEvent(new CustomEvent('omnix:assistant-live-voice-call-connected'));
    window.dispatchEvent(new CustomEvent('omnix:assistant-audio-playback-state', { detail: { speaking: true } }));
    window.dispatchEvent(new CustomEvent('omnix:assistant-live-voice-user-speech', {
      detail: { assistantSpeaking: true },
    }));

    expect(liveConversationStore.getState().conversation).toMatchObject({
      userTurn: 'speech_candidate',
      floorOwner: 'assistant',
      bargeIn: 'confirming',
    });

    window.dispatchEvent(new CustomEvent('omnix:assistant-voice-perf', {
      detail: { stage: 'barge_in_acoustic_candidate', decision: 'likely_echo' },
    }));
    expect(liveConversationStore.getState().conversation).toMatchObject({
      userTurn: 'listening',
      floorOwner: 'assistant',
      bargeIn: 'inactive',
    });
  });

  it('stores calibration evidence safely until the current device pair is verified', () => {
    window.dispatchEvent(new CustomEvent('omnix:live-voice-calibration-updated', {
      detail: {
        version: 'live-voice-calibration-v1',
        deviceKey: 'pair',
        createdAt: Date.now(),
        expiresAt: Date.now() + 60_000,
        noiseFloorRms: 0.002,
        playbackRms: 0.04,
        echoGain: 0.2,
        delayMs: 40,
        similarity: 0.9,
        userSpeechSeparation: 2.5,
        confidence: 0.91,
        resolvedMode: 'echo_aware',
        reason: 'calibration_confident',
      },
    }));
    window.dispatchEvent(new CustomEvent('omnix:live-speech-delivery-plan', {
      detail: {
        speech_act: 'reassurance', energy: 'low', warmth: 'high', certainty: 'moderate',
        pace: 'slightly_slow', clause_pause: 'long', emphasis: [],
      },
    }));

    expect(liveConversationStore.getState().duplex).toMatchObject({
      resolvedMode: 'half_duplex', reason: 'calibration_device_unverified', confidence: 0.91,
    });
    expect(liveConversationStore.getState().deliveryPlan).toMatchObject({
      speech_act: 'reassurance', warmth: 'high',
    });
  });

  it("loads the selected session's profile for the call, whichever view is open", async () => {
    const replies = new Map<string, (profile: Partial<LiveConversationProfile>) => void>();
    vi.mocked(liveConversationProfileClient.get).mockImplementation((sessionId) => new Promise((resolve) => {
      replies.set(sessionId, (effective) => resolve({ effective } as never));
    }));

    emitOmnixEvent('omnix:chat-session-selected', { sessionId: 'chat:older', session: undefined });
    emitOmnixEvent('omnix:chat-session-selected', { sessionId: 'chat:newer', session: undefined });
    replies.get('chat:newer')?.({ duplex_mode: 'echo_aware' });
    await vi.waitFor(() => expect(liveConversationStore.getState().profile?.duplex_mode).toBe('echo_aware'));
    replies.get('chat:older')?.({ duplex_mode: 'half_duplex' });
    await Promise.resolve();

    expect(liveConversationStore.getState().profile?.duplex_mode).toBe('echo_aware');
    emitOmnixEvent('omnix:chat-session-selected', { sessionId: null, session: undefined });
  });
});
