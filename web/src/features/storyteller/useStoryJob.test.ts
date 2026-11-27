import { describe, expect, it } from 'vitest';
import { jobFailureMessage, settledJobFeedback } from './useStoryJob';

describe('story job feedback', () => {
  it('explains the story failure codes instead of showing them', () => {
    expect(settledJobFeedback('rewrite', false, 'failed', 'story_selection_page_changed', true)).toEqual({
      kind: 'error',
      message: 'The page changed after that passage was selected. Select it again and retry.',
    });
    expect(jobFailureMessage('story_beat_not_found')).toBe('That beat is no longer in the plan.');
  });

  it('keeps a sentence the server wrote, and hides an unknown bare code', () => {
    expect(jobFailureMessage('LLM provider is unavailable')).toBe('LLM provider is unavailable');
    expect(jobFailureMessage('story_something_new')).toBe('The story job did not finish.');
    expect(jobFailureMessage(undefined)).toBe('The story job did not finish.');
  });
});
