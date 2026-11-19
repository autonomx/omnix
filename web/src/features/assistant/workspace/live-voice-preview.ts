/** Authoritative transcript previews during a pause, and barge-in assessment while the assistant speaks. */
import { liveConversationStore } from './live-conversation-store';
import { type OverlapAssessment, type OverlapIntent, classifyOverlap, shouldConfirmInterruption } from './live-voice-overlap-classifier';
import { liveCallPresentationStore } from './live-call-presentation-store';
import { AUTHORITATIVE_PREVIEW_PAUSE_MS, LiveVoiceSession, controller, currentAssistantSpeechText, dispatchLiveVoicePerfEvent } from './live-voice-controller-state';
import { onlyRespondToMeActive } from './live-voice-speaker-gate';
import { ASSISTANT_AUDIO_DUCK_EVENT, ASSISTANT_VOICE_INTERRUPT_EVENT, emitOmnixEvent, LIVE_STT_SPECULATION_CANDIDATE_EVENT, LIVE_STT_SPECULATION_PARTIAL_EVENT } from '../../../events/bus';

/** The reply's level while a deferred interruption waits for its voice, as while the overlap judge decides. */
export const SPEAKER_PENDING_GAIN = 0.18;
/** A deferral whose final never comes stops ducking the reply after this long; it still waits for the final. */
export const SPEAKER_PENDING_UNDUCK_MS = 8_000;

export function scheduleAuthoritativePreview(session: LiveVoiceSession): void {
  if (session.previewTimer || session.previewRequestId || session.finalRequested) return;
  session.previewTimer = setTimeout(() => {
    session.previewTimer = null;
    if (
      controller.activeSession !== session
      || session.finalRequested
      || session.pauseStartedAt === null
      || !session.speechDetected
    ) return;
    session.previewRequestId = session.client.requestAuthoritativePreview();
    dispatchLiveVoicePerfEvent({
      stage: 'stt_authoritative_preview_requested',
      turnId: session.perfTurnId,
      timestamp: new Date().toISOString(),
      requested: session.previewRequestId !== null,
      pauseElapsedMs: Math.round(performance.now() - session.pauseStartedAt),
    });
  }, AUTHORITATIVE_PREVIEW_PAUSE_MS);
}

export function handleAuthoritativePreview(
  card: HTMLElement,
  event: {
    segmentId: string;
    sequence: number;
    previewRequestId: string;
    snapshotEndSample: number;
    text: string;
    provider?: string;
    providerMetrics?: Record<string, number>;
  },
): void {
  const session = controller.activeSession;
  const text = event.text.trim();
  if (
    !session
    || session.card !== card
    || (!session.finalRequested && session.pauseStartedAt === null)
    || event.previewRequestId !== session.previewRequestId
    || !text
  ) return;
  session.authoritativePreviewText = text;
  session.speculationSegmentId = event.segmentId;
  session.speculationSourceSequence = event.sequence;
  const detail = {
    chatSessionId: liveConversationStore.getState().sessionId,
    segmentId: event.segmentId,
    sourceSequence: event.sequence,
    text,
  };
  emitOmnixEvent(LIVE_STT_SPECULATION_PARTIAL_EVENT, detail);
  emitOmnixEvent(LIVE_STT_SPECULATION_CANDIDATE_EVENT, {
    ...detail,
    probability: 1,
    modelTimeMs: event.snapshotEndSample * 1_000 / 16_000,
  });
  dispatchLiveVoicePerfEvent({
    stage: 'stt_authoritative_preview_received',
    turnId: session.perfTurnId,
    timestamp: new Date().toISOString(),
    provider: event.provider,
    segmentId: event.segmentId,
    sourceSequence: event.sequence,
    transcriptChars: text.length,
    providerMetrics: event.providerMetrics,
  });
}

export function clearAuthoritativePreview(session: LiveVoiceSession, resumedSpeech = false): void {
  if (resumedSpeech) {
    if (
      session.authoritativePreviewText
      && session.speculationSegmentId
      && session.speculationSourceSequence !== null
      && session.partialTranscript
    ) {
      emitOmnixEvent(LIVE_STT_SPECULATION_PARTIAL_EVENT, {
        chatSessionId: liveConversationStore.getState().sessionId,
        segmentId: session.speculationSegmentId,
        sourceSequence: session.speculationSourceSequence,
        text: session.partialTranscript,
      });
    }
    session.speculationSegmentId = null;
    session.speculationSourceSequence = null;
  }
  if (session.previewTimer) clearTimeout(session.previewTimer);
  session.previewTimer = null;
  session.previewRequestId = null;
  session.authoritativePreviewText = '';
}

export function assessOverlapCandidate(session: LiveVoiceSession): void {
  const assessment = classifyOverlap(session.partialTranscript, currentAssistantSpeechText());
  session.overlapIntent = assessment.intent;
  session.reporter.record('overlap_classified', {
    intent: assessment.intent,
    confidence: assessment.confidence,
    reason: assessment.reason,
    transcript_chars: session.partialTranscript.length,
  }, 'live_voice_controller');
  dispatchLiveVoicePerfEvent({
    stage: 'overlap_classified',
    timestamp: new Date().toISOString(),
    intent: assessment.intent,
    confidence: assessment.confidence,
    reason: assessment.reason,
    transcriptChars: session.partialTranscript.length,
  });
  if (!session.interruptionDispatched && shouldConfirmInterruption(assessment)) {
    session.interruptionDispatched = true;
    if (onlyRespondToMeActive()) deferInterruptForSpeaker(session, assessment.intent, assessment.confidence);
    else dispatchAssistantVoiceInterrupt(session.card, assessment.intent, assessment.confidence);
  }
}

/**
 * "Only respond to me": speech over the reply may be another voice, whose words must not stop it. The interruption waits
 * for the final's voice with the reply ducked, so the caller still hears it give way at once.
 */
export function deferInterruptForSpeaker(
  session: Pick<LiveVoiceSession, 'deferredInterrupt' | 'reporter'>,
  intent: OverlapIntent,
  confidence: number,
): void {
  if (session.deferredInterrupt) return;
  emitOmnixEvent(ASSISTANT_AUDIO_DUCK_EVENT, { ducked: true, gain: SPEAKER_PENDING_GAIN, reason: 'speaker-pending', timestamp: performance.now() });
  const unduckTimer = setTimeout(unduckSpeakerPending, SPEAKER_PENDING_UNDUCK_MS);
  session.deferredInterrupt = { intent, confidence, unduckTimer };
  session.reporter.record('interruption_deferred_for_speaker', { intent, confidence }, 'live_voice_controller');
}

/**
 * Ends a deferral: `dispatch` stops the reply (the caller's voice, or no verdict) if it is still playing, otherwise it
 * plays on. The reply is unducked either way. True when an interruption was dispatched.
 */
export function settleDeferredInterrupt(
  session: Pick<LiveVoiceSession, 'card' | 'deferredInterrupt'>,
  dispatch: boolean,
  assistantSpeaking: boolean,
): boolean {
  const deferred = session.deferredInterrupt;
  if (!deferred) return false;
  session.deferredInterrupt = null;
  clearTimeout(deferred.unduckTimer);
  unduckSpeakerPending();
  if (!dispatch || !assistantSpeaking) return false;
  dispatchAssistantVoiceInterrupt(session.card, deferred.intent, deferred.confidence);
  return true;
}

function unduckSpeakerPending(): void {
  emitOmnixEvent(ASSISTANT_AUDIO_DUCK_EVENT, { ducked: false, gain: 1, reason: 'speaker-settled', timestamp: performance.now() });
}

/**
 * A turn that began over the assistant's speech and has not interrupted it. It is assessed on every transcript, in
 * any floor state: a one-word "stop" has paused before its first partial arrives.
 */
export function overlapAwaitsInterruption(
  session: Pick<LiveVoiceSession, 'overlapIntent' | 'interruptionDispatched'>,
): boolean {
  return session.overlapIntent !== null && !session.interruptionDispatched;
}

/**
 * A partial's intent describes only the words so far: "Yeah" is a backchannel, the sentence it starts is not. The
 * final has all the words, so it decides, except for an interruption already acted on. A turn that began just before
 * the reply's audio started has no partial intent, but its final lands on the assistant's speech all the same.
 */
export function assessFinalOverlap(
  partialIntent: OverlapIntent | null,
  transcript: string,
  assistantText = '',
  assistantSpeaking = false,
): OverlapAssessment | null {
  if (partialIntent === 'interrupt' || (partialIntent === null && !assistantSpeaking)) return null;
  return classifyOverlap(transcript, assistantText);
}

/** A final transcript that confirms an interruption the partials did not: the assistant still speaking stops. */
export function interruptOnFinalOverlap(
  session: Pick<LiveVoiceSession, 'card' | 'interruptionDispatched'>,
  assessment: OverlapAssessment | null,
  assistantSpeaking: boolean,
): void {
  if (!assessment || !assistantSpeaking || session.interruptionDispatched) return;
  if (!shouldConfirmInterruption(assessment)) return;
  session.interruptionDispatched = true;
  dispatchAssistantVoiceInterrupt(session.card, assessment.intent, assessment.confidence);
}

export function dispatchAssistantVoiceInterrupt(
  card: HTMLElement,
  intent: OverlapIntent = 'interrupt',
  confidence = 1,
): void {
  emitOmnixEvent(ASSISTANT_VOICE_INTERRUPT_EVENT, {
      source: 'live-voice',
      status: liveCallPresentationStore.getState().captureStatus,
      timestamp: new Date().toISOString(),
      intent,
      confidence,
    });
}
