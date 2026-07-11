import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { initializeLiveConversationStoreBridge } from './live-conversation-store-bridge';
import { liveConversationStore } from './live-conversation-store';

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

  it('projects calibrated duplex and delivery metadata without DOM inference', () => {
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
      resolvedMode: 'echo_aware', reason: 'calibration_confident', confidence: 0.91,
    });
    expect(liveConversationStore.getState().deliveryPlan).toMatchObject({
      speech_act: 'reassurance', warmth: 'high',
    });
  });
});
