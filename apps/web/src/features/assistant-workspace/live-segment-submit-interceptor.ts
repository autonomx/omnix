import { liveConversationStore } from './live-conversation-store';
import {
  LIVE_COORDINATION_SUBMIT_EVENT,
  liveSessionCoordinator,
  type CoordinateLiveTranscriptInput,
} from './live-session-coordinator';

const LIVE_VOICE_PERF_EVENT = 'omnix:assistant-voice-perf';

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
    if (detail.stage === 'stt_final_received' && this.segmentedActive) {
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
    if (!this.segmentedActive || !this.pendingVoiceFinal) return false;
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
}

export const liveSegmentSubmitInterceptor = new LiveSegmentSubmitInterceptor({
  coordinate: (input) => liveSessionCoordinator.coordinate(input),
  assistantSpeaking: () => liveConversationStore.getState().conversation.assistantTurn === 'speaking',
});

let initialized = false;

export function initializeLiveSegmentSubmitInterceptor(): void {
  if (initialized || typeof window === 'undefined' || typeof document === 'undefined') return;
  initialized = true;
  window.addEventListener(LIVE_VOICE_PERF_EVENT, (event) => {
    const detail = (event as CustomEvent<Record<string, unknown>>).detail;
    if (detail) liveSegmentSubmitInterceptor.observePerformanceEvent(detail);
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
