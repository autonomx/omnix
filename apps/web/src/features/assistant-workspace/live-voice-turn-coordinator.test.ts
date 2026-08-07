import { describe, expect, it, vi } from 'vitest';

import {
  LIVE_VOICE_TURN_TIMELINE_EVENT,
  LiveVoiceTurnCoordinator,
  endpointFusionAction,
  type LiveVoiceTurnTimelineDetail,
} from './live-voice-turn-coordinator';

describe('live voice turn coordinator', () => {
  it('keeps one immutable speech-end timestamp per turn', () => {
    const coordinator = new LiveVoiceTurnCoordinator();
    const events: LiveVoiceTurnTimelineDetail[] = [];
    const listener = (event: Event) => events.push(
      (event as CustomEvent<LiveVoiceTurnTimelineDetail>).detail,
    );
    window.addEventListener(LIVE_VOICE_TURN_TIMELINE_EVENT, listener);

    coordinator.speechEnded('voice-turn:one', 100);
    coordinator.speechEnded('voice-turn:one', 150);
    coordinator.finalReceived('voice-turn:one', 220);

    expect(coordinator.snapshot('voice-turn:one')).toMatchObject({
      state: 'committed',
      speechEndedAt: 100,
      finalReceivedAt: 220,
    });
    expect(events.map((event) => event.event)).toEqual([
      'speech_ended',
      'final_received',
    ]);
    window.removeEventListener(LIVE_VOICE_TURN_TIMELINE_EVENT, listener);
  });

  it('fuses endpoint confidence, stability, and silence into one action', () => {
    expect(endpointFusionAction({
      endpointProbability: 0.8,
      endpointThreshold: 0.75,
      silenceMs: 170,
      transcriptStableMs: 100,
      semanticProbabilityDone: 0.94,
      transcriptWords: 4,
      correctionPending: false,
    })).toBe('commit');
    expect(endpointFusionAction({
      endpointProbability: 0.48,
      endpointThreshold: 0.75,
      silenceMs: 40,
      transcriptStableMs: 80,
      semanticProbabilityDone: 0.7,
      transcriptWords: 4,
      correctionPending: false,
    })).toBe('speculate');
    expect(endpointFusionAction({
      endpointProbability: 0.95,
      endpointThreshold: 0.75,
      silenceMs: 300,
      transcriptStableMs: 100,
      semanticProbabilityDone: 0.95,
      transcriptWords: 3,
      correctionPending: true,
    })).toBe('continue');
  });

  it('emits timeline events using the supplied monotonic timestamp', () => {
    const coordinator = new LiveVoiceTurnCoordinator();
    const listener = vi.fn();
    window.addEventListener(LIVE_VOICE_TURN_TIMELINE_EVENT, listener);
    coordinator.playbackStarted('voice-turn:play', 440);
    expect(listener).toHaveBeenCalledOnce();
    const detail = (listener.mock.calls[0][0] as CustomEvent<LiveVoiceTurnTimelineDetail>).detail;
    expect(detail).toMatchObject({
      turnId: 'voice-turn:play',
      event: 'playback_started',
      atMs: 440,
      state: 'playing',
    });
    window.removeEventListener(LIVE_VOICE_TURN_TIMELINE_EVENT, listener);
  });
});
