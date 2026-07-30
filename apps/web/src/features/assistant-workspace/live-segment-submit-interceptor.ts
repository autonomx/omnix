import { liveConversationStore } from './live-conversation-store';

const LIVE_VOICE_PERF_EVENT = 'omnix:assistant-voice-perf';

type LiveSegmentObserverWindow = Window & typeof globalThis & {
  __omnixLiveSegmentObserverInstalled?: boolean;
};

export class LiveSegmentStateObserver {
  private segmentedActive = false;

  observePerformanceEvent(detail: Record<string, unknown>): void {
    if (detail.stage === 'stt_segment_state') {
      this.segmentedActive = detail.protocol === 'segmented-v1';
    }
  }

  reset(): void {
    this.segmentedActive = false;
  }

  get protocol(): 'legacy' | 'segmented-v1' {
    return this.segmentedActive ? 'segmented-v1' : 'legacy';
  }
}

export const liveSegmentStateObserver = new LiveSegmentStateObserver();

let initialized = false;

export function initializeLiveSegmentSubmitInterceptor(): void {
  if (initialized || typeof window === 'undefined') return;
  const liveWindow = window as LiveSegmentObserverWindow;
  if (liveWindow.__omnixLiveSegmentObserverInstalled) return;
  initialized = true;
  liveWindow.__omnixLiveSegmentObserverInstalled = true;
  window.addEventListener(LIVE_VOICE_PERF_EVENT, (event) => {
    const detail = (event as CustomEvent<Record<string, unknown>>).detail;
    if (!detail) return;
    liveSegmentStateObserver.observePerformanceEvent(detail);
    if (detail.stage === 'stt_segment_state') {
      const pendingSegments = typeof detail.pendingSegments === 'number' ? detail.pendingSegments : 0;
      liveConversationStore.dispatch({ type: 'pending_segments', count: pendingSegments });
      liveConversationStore.dispatch({
        type: 'capture_activity',
        activity: detail.protocol === 'segmented-v1' ? 'capturing' : 'idle',
      });
    }
    if (detail.stage === 'stt_finalization_buffer_overflow' || detail.stage === 'stt_final_rejected') {
      liveConversationStore.dispatch({ type: 'capture_activity', activity: 'degraded' });
    }
  });
  window.addEventListener('beforeunload', () => liveSegmentStateObserver.reset());
}
