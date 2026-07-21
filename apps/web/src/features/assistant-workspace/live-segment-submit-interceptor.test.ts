import { describe, expect, it, vi } from 'vitest';

import { LiveSegmentSubmitInterceptor } from './live-segment-submit-interceptor';

describe('LiveSegmentSubmitInterceptor', () => {
  it('routes a voice final through coordination even before segmented negotiation', () => {
    const coordinate = vi.fn(async () => undefined);
    const interceptor = new LiveSegmentSubmitInterceptor({
      coordinate,
      assistantSpeaking: () => true,
    });

    interceptor.observePerformanceEvent({ stage: 'stt_final_received' });

    expect(interceptor.protocol).toBe('legacy');
    expect(interceptor.intercept('Translate this continuously.')).toBe(true);
    expect(coordinate).toHaveBeenCalledWith({
      text: 'Translate this continuously.',
      segmentId: 'stt-segment-0',
      sourceSequence: 0,
      assistantSpeaking: true,
      acousticClass: 'speech',
    });
  });

  it('keeps ordinary typed composer submissions outside the voice coordinator', () => {
    const coordinate = vi.fn(async () => undefined);
    const interceptor = new LiveSegmentSubmitInterceptor({
      coordinate,
      assistantSpeaking: () => false,
    });

    expect(interceptor.intercept('Typed message')).toBe(false);
    expect(coordinate).not.toHaveBeenCalled();
  });

  it('permits the coordinator to submit a conversational response exactly once', () => {
    const coordinate = vi.fn(async () => undefined);
    const interceptor = new LiveSegmentSubmitInterceptor({
      coordinate,
      assistantSpeaking: () => false,
    });

    interceptor.observePerformanceEvent({ stage: 'stt_final_received' });
    interceptor.permitNextCoordinatedSubmit();

    expect(interceptor.intercept('Question for Maya')).toBe(false);
    expect(interceptor.intercept('Question for Maya')).toBe(true);
    expect(coordinate).toHaveBeenCalledTimes(1);
  });

  it('records segmented protocol state without making routing depend on it', () => {
    const coordinate = vi.fn(async () => undefined);
    const interceptor = new LiveSegmentSubmitInterceptor({
      coordinate,
      assistantSpeaking: () => false,
    });

    interceptor.observePerformanceEvent({ stage: 'stt_segment_state', protocol: 'segmented-v1' });
    interceptor.observePerformanceEvent({ stage: 'stt_final_received' });

    expect(interceptor.protocol).toBe('segmented-v1');
    expect(interceptor.intercept('Ongoing material')).toBe(true);
    expect(coordinate).toHaveBeenCalledTimes(1);
  });
});
