import { describe, expect, it } from 'vitest';

import { replayLiveConversation } from './live-conversation-replay';

describe('replayLiveConversation', () => {
  it('replays timestamped state and actions deterministically', () => {
    const result = replayLiveConversation([
      { atMs: 300, event: { type: 'assistant_turn', value: 'speaking' }, action: 'continue' },
      { atMs: 0, event: { type: 'connection', value: 'connected' } },
      { atMs: 100, event: { type: 'user_turn', value: 'speaking' }, action: 'wait' },
      { atMs: 100, event: { type: 'floor_owner', value: 'user' } },
      { atMs: 250, event: { type: 'user_turn', value: 'completion_pending' }, action: 'finalize' },
    ], undefined, 'Maya');

    expect(result.frames.map((frame) => frame.atMs)).toEqual([0, 100, 100, 250, 300]);
    expect(result.actions).toEqual(['wait', 'finalize', 'continue']);
    expect(result.frames[2]?.state.floorOwner).toBe('user');
    expect(result.frames[3]?.visibleStatus).toBe('Waiting for you');
    expect(result.finalState.assistantTurn).toBe('speaking');
  });

  it('rejects invalid timestamps', () => {
    expect(() => replayLiveConversation([
      { atMs: -1, event: { type: 'connection', value: 'connected' } },
    ])).toThrow('Replay timestamps must be finite and non-negative.');
  });
});
