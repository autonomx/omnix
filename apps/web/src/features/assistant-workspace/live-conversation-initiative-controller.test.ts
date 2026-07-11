import { describe, expect, it } from 'vitest';

import {
  parseProactiveSse,
  proactiveReasonFromTranscript,
} from './live-conversation-initiative-controller';

describe('live conversation initiative controller', () => {
  it('parses transient proactive stream metadata and content', () => {
    const parsed = parseProactiveSse([
      'data: {"type":"initiative","turn_id":"proactive:one","initiative_reason":"unresolved_question"}',
      '',
      'data: {"type":"complete","content":"Want to keep working through that?","metadata":{"turn_id":"proactive:one"}}',
      '',
      'data: {"type":"done"}',
      '',
    ].join('\n'));

    expect(parsed).toEqual({
      turnId: 'proactive:one',
      content: 'Want to keep working through that?',
      initiativeReason: 'unresolved_question',
    });
  });

  it('surfaces server errors instead of silently discarding them', () => {
    expect(() => parseProactiveSse('data: {"type":"error","message":"Provider unavailable"}\n\n'))
      .toThrow('Provider unavailable');
  });

  it('derives only context-backed initiative reasons from authoritative transcript text', () => {
    expect(proactiveReasonFromTranscript('Should we revisit the launch plan?')).toBe('unresolved_question');
    expect(proactiveReasonFromTranscript('The launch plan is still open.')).toBe('continue_current_topic');
    expect(proactiveReasonFromTranscript('')).toBeNull();
  });
});
