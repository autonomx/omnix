import {
  INITIAL_LIVE_CONVERSATION_STATE,
  deriveLiveConversationStatus,
  reduceLiveConversationState,
  type LiveConversationState,
  type LiveConversationStateEvent,
} from './live-conversation-state';

export type LiveConversationAction =
  | 'wait'
  | 'finalize'
  | 'duck'
  | 'cancel'
  | 'continue'
  | 'backchannel'
  | 'repair'
  | 'proactive_speak'
  | 'suppress';

export type TimedLiveConversationEvent = {
  atMs: number;
  event: LiveConversationStateEvent;
  action?: LiveConversationAction;
};

export type LiveConversationReplayFrame = {
  atMs: number;
  state: LiveConversationState;
  visibleStatus: string;
  action: LiveConversationAction | null;
};

export type LiveConversationReplayResult = {
  frames: LiveConversationReplayFrame[];
  actions: LiveConversationAction[];
  finalState: LiveConversationState;
};

export function replayLiveConversation(
  events: TimedLiveConversationEvent[],
  initialState: LiveConversationState = INITIAL_LIVE_CONVERSATION_STATE,
  characterName = 'Assistant',
): LiveConversationReplayResult {
  const ordered = events
    .map((event, index) => ({ event, index }))
    .sort((left, right) => left.event.atMs - right.event.atMs || left.index - right.index);
  let state = initialState;
  const frames: LiveConversationReplayFrame[] = [];
  const actions: LiveConversationAction[] = [];

  for (const { event } of ordered) {
    if (!Number.isFinite(event.atMs) || event.atMs < 0) throw new Error('Replay timestamps must be finite and non-negative.');
    state = reduceLiveConversationState(state, event.event);
    if (event.action) actions.push(event.action);
    frames.push({
      atMs: event.atMs,
      state,
      visibleStatus: deriveLiveConversationStatus(state, characterName),
      action: event.action ?? null,
    });
  }

  return { frames, actions, finalState: state };
}
