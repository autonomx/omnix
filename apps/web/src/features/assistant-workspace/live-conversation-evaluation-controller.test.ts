import { beforeEach, describe, expect, it } from 'vitest';

import {
  evaluationEventFromPerfDetail,
  readLiveConversationEvaluationSnapshot,
  recordLiveConversationEvaluationEvent,
  recordLiveConversationSurvey,
  resetLiveConversationEvaluation,
} from './live-conversation-evaluation-controller';

describe('live conversation evaluation controller', () => {
  beforeEach(() => {
    window.localStorage.clear();
    resetLiveConversationEvaluation();
  });

  it('maps structured voice diagnostics without guessing unsupported metrics', () => {
    expect(evaluationEventFromPerfDetail({ stage: 'voice_audio_turnaround', total_ms: 840 }, 10))
      .toEqual({ atMs: 10, type: 'first_audio', latencyMs: 840 });
    expect(evaluationEventFromPerfDetail({ stage: 'endpoint_false_positive' }, 20))
      .toEqual({ atMs: 20, type: 'endpoint', falsePositive: true });
    expect(evaluationEventFromPerfDetail({
      stage: 'overlap_classified', intent: 'correction', cancellation_latency_ms: 120,
    }, 30)).toEqual({ atMs: 30, type: 'interruption', success: true, latencyMs: 120 });
    expect(evaluationEventFromPerfDetail({ stage: 'overlap_classified', intent: 'backchannel' }, 40)).toBeNull();
  });

  it('persists bounded events and updates survey scores', () => {
    recordLiveConversationEvaluationEvent({ atMs: 1, type: 'first_audio', latencyMs: 500 });
    recordLiveConversationEvaluationEvent({ atMs: 2, type: 'turn', role: 'assistant', durationMs: 1_000, content: 'Ready?' });
    const snapshot = recordLiveConversationSurvey(5, 2);

    expect(snapshot.report.firstAudioLatencyMs.average).toBe(500);
    expect(snapshot.report.questionDensity).toBe(1);
    expect(snapshot.report.perceivedListeningScore).toBe(5);
    expect(snapshot.report.perceivedPressureScore).toBe(2);
    expect(readLiveConversationEvaluationSnapshot().events).toHaveLength(3);

    const stored = JSON.parse(window.localStorage.getItem('omnix.liveConversation.evaluation.v1') || '[]');
    expect(stored).toHaveLength(3);
  });
});
