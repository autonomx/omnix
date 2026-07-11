import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const report = {
  eventCount: 12,
  firstAudioLatencyMs: { average: 510, p95: 720 },
  falseEndpointRate: 0,
  talkOverDurationMs: 80,
  interruptionSuccessRate: 1,
  cancellationLatencyMs: { average: 120, p95: 180 },
  silenceFillRegretRate: 0.1,
  proactiveAcceptanceRate: 0.8,
  backchannelCollisionRate: 0,
  questionDensity: 0.3,
  assistantUserSpeakingRatio: 0.8,
  turnDurationMs: { median: 1_500, p95: 4_000 },
  repairSuccessRate: 1,
  repeatedTopicRate: 0,
  unansweredObligationRate: 0,
  perceivedListeningScore: 5,
  perceivedPressureScore: 1,
};

vi.mock('./live-conversation-evaluation-controller', () => ({
  readLiveConversationEvaluationSnapshot: () => ({ events: [], report }),
}));

import {
  buildDurableEvaluationPayload,
  initializeLiveConversationDurableEvaluationController,
} from './live-conversation-durable-evaluation-controller';
import { liveConversationStore } from './live-conversation-store';

const profile = {
  presence_preset: 'natural' as const,
  talkativeness: 50,
  conversation_stance: 'discuss' as const,
  conversation_pace: 'balanced' as const,
  interruption_preference: 'balanced' as const,
  assistant_backchannel_mode: 'natural' as const,
  initiative_mode: 'gentle' as const,
  idle_threshold_ms: 15_000,
  long_pause_behavior: 'wait' as const,
  response_length: 'conversational' as const,
  response_onset_style: 'adaptive' as const,
  emotional_attunement: 'subtle' as const,
  topic_continuity: 'natural' as const,
  max_idle_prompts: 1,
  duplex_mode: 'automatic' as const,
  pronunciation_save_policy: 'ask' as const,
  profile_version: 2,
};

describe('durable Live Conversation evaluation controller', () => {
  beforeEach(() => {
    window.localStorage.clear();
    liveConversationStore.reset();
    liveConversationStore.dispatch({ type: 'session', sessionId: 'chat:maya' });
    liveConversationStore.dispatch({ type: 'identity', identity: { characterId: 'maya', displayName: 'Maya', profileVersion: 4 } });
    liveConversationStore.dispatch({ type: 'profile', profile });
    liveConversationStore.dispatch({
      type: 'duplex',
      duplex: {
        configuredMode: 'automatic',
        resolvedMode: 'echo_aware',
        reason: 'calibration_confident',
        confidence: 0.91,
        calibration: {
          version: 'live-voice-calibration-v1',
          deviceKey: 'device-pair-hash',
          createdAt: 1_000,
          expiresAt: Date.now() + 60_000,
          noiseFloorRms: 0.002,
          playbackRms: 0.04,
          echoGain: 0.2,
          delayMs: 42,
          similarity: 0.9,
          userSpeechSeparation: 2.4,
          confidence: 0.91,
          resolvedMode: 'echo_aware',
          reason: 'calibration_confident',
        },
      },
    });
    document.documentElement.dataset.commitSha = 'a'.repeat(40);
    document.documentElement.dataset.appVersion = '1.2.3';
    window.localStorage.setItem('omnix.liveCall.releaseScenario', 'speakers-quiet,immediate-hard-stop');
  });

  afterEach(() => {
    delete document.documentElement.dataset.commitSha;
    delete document.documentElement.dataset.appVersion;
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('builds aggregate-only evidence from the authoritative store', () => {
    const payload = buildDurableEvaluationPayload({
      callId: 'call-one',
      startedAt: '2026-07-11T12:00:00+00:00',
      eosTerminationCounts: { natural_eos: 6, forced_eos: 1, token_limit: 0, sequence_limit: 0, model_stopped: 0 },
    }, '2026-07-11T12:10:00+00:00');

    expect(payload).toMatchObject({
      call_id: 'call-one',
      session_id: 'chat:maya',
      character_id: 'maya',
      presence_preset: 'natural',
      resolved_duplex_mode: 'echo_aware',
      listening_score: 5,
      pressure_score: 1,
      eos_termination_counts: { natural_eos: 6, forced_eos: 1 },
      scenario_labels: ['speakers-quiet', 'immediate-hard-stop'],
    });
    const serialized = JSON.stringify(payload).toLocaleLowerCase();
    expect(serialized).not.toMatch(/transcript|prompt|memory|pcm|message_content|utterance_text/);
  });

  it('posts one record on call stop and counts EOS reasons', async () => {
    const fetchMock = vi.fn(async () => Response.json({ evaluation_id: 'evaluation-one' }));
    vi.stubGlobal('fetch', fetchMock);
    const dispose = initializeLiveConversationDurableEvaluationController();

    window.dispatchEvent(new CustomEvent('omnix:assistant-live-voice-call-start'));
    window.dispatchEvent(new CustomEvent('omnix:assistant-voice-perf', {
      detail: { provider_timing: { termination_reason: 'natural_eos' } },
    }));
    window.dispatchEvent(new CustomEvent('omnix:assistant-live-voice-stop'));
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const body = JSON.parse(String(init.body));
    expect(body.eos_termination_counts.natural_eos).toBe(1);
    expect(body.release_gate_status).toBe('insufficient');
    dispose();
  });
});
