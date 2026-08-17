import type { LiveConversationReplayResult } from './live-conversation-replay';
import type { LiveConversationEvaluationEvent } from './live-conversation-evaluation';

export function evaluationEventsFromReplay(
  replay: LiveConversationReplayResult,
): LiveConversationEvaluationEvent[] {
  const events: LiveConversationEvaluationEvent[] = [];
  let previousAt = 0;
  for (const frame of replay.frames) {
    const durationMs = Math.max(0, frame.atMs - previousAt);
    previousAt = frame.atMs;
    switch (frame.action) {
      case 'finalize':
        events.push({ atMs: frame.atMs, type: 'endpoint', falsePositive: false });
        break;
      case 'duck':
        events.push({ atMs: frame.atMs, type: 'talk_over', durationMs });
        break;
      case 'cancel':
        events.push({ atMs: frame.atMs, type: 'interruption', success: true, latencyMs: durationMs });
        break;
      case 'backchannel':
        events.push({ atMs: frame.atMs, type: 'backchannel', collision: false });
        break;
      case 'repair':
        events.push({ atMs: frame.atMs, type: 'repair', success: true });
        break;
      case 'proactive_speak':
        events.push({ atMs: frame.atMs, type: 'proactive_prompt', accepted: null });
        break;
      default:
        break;
    }
  }
  return events;
}
