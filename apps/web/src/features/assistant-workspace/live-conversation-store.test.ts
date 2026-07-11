import { describe, expect, it } from 'vitest';

import {
  INITIAL_LIVE_CONVERSATION_RUNTIME_STATE,
  createLiveConversationStore,
  replayLiveConversationActions,
  selectLiveChatSnapshot,
  type LiveConversationStoreAction,
} from './live-conversation-store';

const replay: LiveConversationStoreAction[] = [
  { type: 'session', sessionId: 'chat:maya' },
  { type: 'identity', identity: { characterId: 'maya', displayName: 'Maya', profileVersion: 4 } },
  { type: 'conversation', event: { type: 'connection', value: 'connected' } },
  { type: 'conversation', event: { type: 'user_turn', value: 'speaking' } },
  { type: 'conversation', event: { type: 'floor_owner', value: 'user' } },
  { type: 'transcript_partial', text: 'I was thinking' },
  { type: 'transcript_final', text: 'I was thinking about the launch.' },
  { type: 'conversation', event: { type: 'user_turn', value: 'finalizing' } },
  { type: 'conversation', event: { type: 'assistant_turn', value: 'generating' } },
  { type: 'conversation', event: { type: 'assistant_turn', value: 'speaking' } },
  { type: 'conversation', event: { type: 'delivery', value: 'audio_started' } },
  { type: 'conversation', event: { type: 'floor_owner', value: 'assistant' } },
];

describe('live conversation store', () => {
  it('replays the same timestamp-ordered action stream deterministically', () => {
    const first = replayLiveConversationActions(replay);
    const second = replayLiveConversationActions(replay);

    expect(first).toEqual(second);
    expect(first.sessionId).toBe('chat:maya');
    expect(first.identity.displayName).toBe('Maya');
    expect(first.transcript.recentFinals).toEqual(['I was thinking about the launch.']);
    expect(selectLiveChatSnapshot(first)).toMatchObject({
      connected: true,
      identity: 'Maya',
      state: 'Maya is speaking',
      floorOwner: 'assistant',
    });
  });

  it('keeps orthogonal state domains independent and observable', () => {
    const store = createLiveConversationStore();
    let notifications = 0;
    const unsubscribe = store.subscribe(() => { notifications += 1; });

    store.dispatch({ type: 'duplex', duplex: { resolvedMode: 'echo_aware', reason: 'calibration_confident', confidence: 0.91 } });
    store.dispatch({ type: 'conversation', event: { type: 'barge_in', value: 'ducking' } });
    store.dispatch({ type: 'quality', summary: { perceivedListeningScore: 5 } });

    expect(store.getState().duplex.resolvedMode).toBe('echo_aware');
    expect(store.getState().conversation.bargeIn).toBe('ducking');
    expect(store.getState().qualitySummary).toEqual({ perceivedListeningScore: 5 });
    expect(store.getState().conversation.connection).toBe('disconnected');
    expect(notifications).toBe(3);
    unsubscribe();
  });

  it('resets conversation activity without losing session identity or calibration', () => {
    const state = replayLiveConversationActions([
      ...replay,
      { type: 'duplex', duplex: { resolvedMode: 'echo_aware', reason: 'calibration_confident', confidence: 0.9 } },
      { type: 'reset_conversation' },
    ]);

    expect(state.conversation).toEqual(INITIAL_LIVE_CONVERSATION_RUNTIME_STATE.conversation);
    expect(state.sessionId).toBe('chat:maya');
    expect(state.identity.displayName).toBe('Maya');
    expect(state.duplex.resolvedMode).toBe('echo_aware');
  });
});
