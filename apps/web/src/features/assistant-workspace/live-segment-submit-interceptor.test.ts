import { describe, expect, it } from 'vitest';

import { LiveSegmentStateObserver } from './live-segment-submit-interceptor';

describe('LiveSegmentStateObserver', () => {
  it('records segmented protocol state without owning submission behavior', () => {
    const observer = new LiveSegmentStateObserver();

    expect(observer.protocol).toBe('legacy');
    observer.observePerformanceEvent({ stage: 'stt_segment_state', protocol: 'segmented-v1' });
    expect(observer.protocol).toBe('segmented-v1');

    observer.observePerformanceEvent({ stage: 'stt_final_received' });
    expect(observer.protocol).toBe('segmented-v1');

    observer.reset();
    expect(observer.protocol).toBe('legacy');
  });
});
