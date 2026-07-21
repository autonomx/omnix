import { liveConversationStore } from './live-conversation-store';
import {
  LIVE_COORDINATION_SUBMIT_EVENT,
  liveSessionCoordinator,
  type CoordinateLiveTranscriptInput,
} from './live-session-coordinator';

const LIVE_VOICE_PERF_EVENT = 'omnix:assistant-voice-perf';

type LiveSegmentSubmitWindow = Window & typeof globalThis & {
  __omnixLiveSegmentSubmitInterceptorInstalled?: boolean;
};

export type LiveSegmentSubmitDependencies = {
  coordinate: (input: CoordinateLiveTranscriptInput) => Promise<unknown>;
  assistantSpeaking: () => boolean;
};

export class LiveSegmentSubmitInterceptor {
  private segmentedActive = false;
  private pendingVoiceFinal = false;
  private allowCoordinatedSubmit = false;
  private sourceSequence = 0;

  constructor(private readonly dependencies: LiveSegmentSubmitDependencies) {}

  observePerformanceEvent(detail: Record<string, unknown>): void {
    if (detail.stage === 'stt_segment_state') {
      this.segmentedActive = detail.protocol === 'segmented-v1';
      return;
    }
    if (detail.stage === 'stt_final_received') {
      // Semantic routing must not depend on protocol negotiation. A stale or
      // compatibility STT process may use the legacy wire format, but its Live
      // finals still represent voice input and must not silently become ordinary
      // composer turns that supersede active translation output.
      this.pendingVoiceFinal = true;
    }
  }

  permitNextCoordinatedSubmit(): void {
    this.allowCoordinatedSubmit = true;
  }

  intercept(text: string): boolean {
    if (this.allowCoordinatedSubmit) {
      this.allowCoordinatedSubmit = false;
      return false;
    }
    if (!this.pendingVoiceFinal) return false;
    this.pendingVoiceFinal = false;
    const normalized = text.trim();
    if (!normalized) return true;
    const sourceSequence = this.sourceSequence;
    this.sourceSequence += 1;
    void this.dependencies.coordinate({
      text: normalized,
      segmentId: `stt-segment-${sourceSequence}`,
      sourceSequence,
      assistantSpeaking: this.dependencies.assistantSpeaking(),
      acousticClass: 'speech',
    });
    return true;
  }

  reset(): void {
    this.segmentedActive = false;
    this.pendingVoiceFinal = false;
    this.allowCoordinatedSubmit = false;
    this.sourceSequence = 0;
  }

  get protocol(): 'legacy' | 'segmented-v1' {
    return this.segmentedActive ? 'segmented-v1' : 'legacy';
  }
}

export const liveSegmentSubmitInterceptor = new LiveSegmentSubmitInterceptor({
  coordinate: (input) => liveSessionCoordinator.coordinate(input),
  assistantSpeaking: () => liveConversationStore.getState().conversation.assistantTurn === 'speaking',
});

let initialized = false;

export function initializeLiveSegmentSubmitInterceptor(): void {
  if (initialized || typeof window === 'undefined' || typeof document === 'undefined') return;
  const liveWindow = window as LiveSegmentSubmitWindow;
  if (liveWindow.__omnixLiveSegmentSubmitInterceptorInstalled) return;
  initialized = true;
  liveWindow.__omnixLiveSegmentSubmitInterceptorInstalled = true;
  window.addEventListener(LIVE_VOICE_PERF_EVENT, (event) => {
    const detail = (event as CustomEvent<Record<string, unknown>>).detail;
    if (!detail) return;
    liveSegmentSubmitInterceptor.observePerformanceEvent(detail);
    if (detail.stage === 'stt_segment_state') {
      const pendingSegments = typeof detail.pendingSegments === 'number' ? detail.pendingSegments : 0;
      liveConversationStore.dispatch({ type: 'pending_segments', count: pendingSegments });
      liveConversationStore.dispatch({
        type: 'capture_activity',
        activity: detail.protocol === 'segmented-v1' ? 'capturing' : 'idle',
      });
    }
    if (detail.stage === 'stt_finalization_buffer_overflow') {
      liveConversationStore.dispatch({ type: 'capture_activity', activity: 'degraded' });
    }
  });
  window.addEventListener(LIVE_COORDINATION_SUBMIT_EVENT, () => {
    liveSegmentSubmitInterceptor.permitNextCoordinatedSubmit();
  });
  document.addEventListener('submit', (event) => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement) || !form.matches('.assistant-composer')) return;
    const textarea = document.querySelector<HTMLTextAreaElement>('.assistant-message-input textarea');
    if (!liveSegmentSubmitInterceptor.intercept(textarea?.value ?? '')) return;
    event.preventDefault();
    event.stopImmediatePropagation();
  }, true);
  window.addEventListener('beforeunload', () => liveSegmentSubmitInterceptor.reset());
}
