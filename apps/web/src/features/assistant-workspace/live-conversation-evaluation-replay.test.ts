import { describe, expect, it } from 'vitest';

import { replayLiveConversation } from './live-conversation-replay';
import { evaluationEventsFromReplay } from './live-conversation-evaluation-replay';
import { evaluateLiveConversation } from './live-conversation-evaluation';

describe('evaluationEventsFromReplay', () => {
  it('converts deterministic replay actions into evaluation inputs', () => {
    const replay = replayLiveConversation([
      { atMs: 0, event: { type: 'connection', value: 'connected' } },
      { atMs: 100, event: { type: 'user_turn', value: 'completion_pending' }, action: 'finalize' },
      { atMs: 180, event: { type: 'barge_in', value: 'ducking' }, action: 'duck' },
      { atMs: 260, event: { type: 'barge_in', value: 'accepted' }, action: 'cancel' },
      { atMs: 400, event: { type: 'initiative', value: 'prompting' }, action: 'proactive_speak' },
      { atMs: 500, event: { type: 'assistant_turn', value: 'speaking' }, action: 'backchannel' },
      { atMs: 600, event: { type: 'assistant_turn', value: 'planning' }, action: 'repair' },
    ]);

    const events = evaluationEventsFromReplay(replay);
    const report = evaluateLiveConversation(events);

    expect(events.map((event) => event.type)).toEqual([
      'endpoint', 'talk_over', 'interruption', 'proactive_prompt', 'backchannel', 'repair',
    ]);
    expect(report.falseEndpointRate).toBe(0);
    expect(report.interruptionSuccessRate).toBe(1);
    expect(report.backchannelCollisionRate).toBe(0);
    expect(report.repairSuccessRate).toBe(1);
  });
});
