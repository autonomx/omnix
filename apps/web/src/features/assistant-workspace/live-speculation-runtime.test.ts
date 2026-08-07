import { describe, expect, it } from 'vitest';

import { liveSubmissionRequestMatches } from './live-speculation-runtime';

const submission = {
  sessionId: 'chat:one',
  text: 'Hello',
  source: 'live_coordination' as const,
  interrupted: false,
  segmentId: 'segment-1',
  sourceSequence: 1,
};

describe('live speculation runtime routing', () => {
  it('matches only the active live submission chat stream', () => {
    expect(liveSubmissionRequestMatches(
      submission,
      '/api/chat/sessions/chat%3Aone/messages/stream',
      { method: 'POST' },
    )).toBe(true);
    expect(liveSubmissionRequestMatches(
      submission,
      '/api/chat/sessions/chat%3Atwo/messages/stream',
      { method: 'POST' },
    )).toBe(false);
    expect(liveSubmissionRequestMatches(
      submission,
      '/api/chat/sessions/chat%3Aone/messages/stream',
      { method: 'GET' },
    )).toBe(false);
  });
});
