import { describe, expect, it } from 'vitest';

import { normalizeEvaluationEvent } from './desktop-companion-shadow-evaluation-controller';

describe('desktop companion evaluation events', () => {
  it('accepts bounded content-free lifecycle facts and effective stage', () => {
    expect(normalizeEvaluationEvent({
      kind: 'vision_result',
      sessionId: 'chat:1',
      rolloutStage: 'text',
      scenario: 'scene-change',
      latencyMs: 1234.5,
      callsThisMinute: 3,
      providerError: false,
      stale: false,
      observed: true,
      reason: 'observation_completed',
    })).toEqual({
      kind: 'vision_result',
      sessionId: 'chat:1',
      characterId: null,
      modelId: null,
      remoteProvider: false,
      rolloutStage: 'text',
      scenario: 'scene-change',
      meaningful: false,
      latencyMs: 1234.5,
      callsThisMinute: 3,
      providerError: false,
      stale: false,
      observed: true,
      reason: 'observation_completed',
    });
  });

  it('rejects unknown event types and ignores content-bearing extras', () => {
    expect(normalizeEvaluationEvent({ kind: 'frame', sessionId: 'chat:1' })).toBeNull();
    const result = normalizeEvaluationEvent({
      kind: 'capture',
      sessionId: 'chat:1',
      scenario: 'typing',
      meaningful: true,
      frame: 'data:image/png;base64,secret',
      screenText: 'secret',
    });
    expect(result).toEqual({
      kind: 'capture',
      sessionId: 'chat:1',
      characterId: null,
      modelId: null,
      remoteProvider: false,
      rolloutStage: undefined,
      scenario: 'typing',
      meaningful: true,
      latencyMs: undefined,
      callsThisMinute: undefined,
      providerError: false,
      stale: false,
      observed: false,
      reason: undefined,
    });
    expect(JSON.stringify(result)).not.toContain('secret');
  });
});
