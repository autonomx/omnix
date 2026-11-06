/** Routes an accepted final transcript to the conversation, or suppresses it. */
import type { AcceptedVoiceFinal, LiveFinalRoutingResult } from './live-accepted-final';
import { acceptedFinalSuppressionReason } from './live-accepted-final-routing';
import { liveConversationStore } from './live-conversation-store';
import { currentLiveRuntimeProvenance } from './live-runtime-provenance';
import { liveSessionCoordinator } from './live-session-coordinator';
import { controller, currentAssistantSpeechText, dispatchLiveVoicePerfEvent, liveVoiceAssistantIsSpeaking, renderTranscript, setPanelStatus, type LiveVoiceSession } from './live-voice-controller-state';
import { assessFinalOverlap, dispatchAssistantVoiceInterrupt, interruptOnFinalOverlap } from './live-voice-preview';
import { replayFinalizationBuffer } from './live-voice-finalization';
import { judgeOverlap } from './live-voice-overlap-judge';
import { resetTurnState } from './live-voice-session-lifecycle';
import { ASSISTANT_AUDIO_DUCK_EVENT, emitOmnixEvent, LIVE_STT_SPECULATION_DELIVERY_SETTLED_EVENT, LIVE_STT_SPECULATION_FINAL_EVENT } from '../../../events/bus';

// The reply sinks at once while the model decides, so the listener hears it give way before they know the outcome.
const JUDGING_GAIN = 0.18;

export async function handleAcceptedFinal(card: HTMLElement, final: AcceptedVoiceFinal): Promise<LiveFinalRoutingResult> {
  const session = controller.activeSession;
  if (!session || session.card !== card) {
    return failedRoutingResult(final, 'live_capture_session_inactive');
  }
  const receivedAt = performance.now();
  const partialOverlapIntent = session.overlapIntent;
  const assistantSpeaking = liveVoiceAssistantIsSpeaking();
  const finalOverlapAssessment = assessFinalOverlap(partialOverlapIntent, final.text, currentAssistantSpeechText(), assistantSpeaking);
  const overlapIntent = finalOverlapAssessment?.intent ?? partialOverlapIntent;
  interruptOnFinalOverlap(session, finalOverlapAssessment, assistantSpeaking);
  const interruptionDispatched = session.interruptionDispatched;
  const suppressionReason = acceptedFinalSuppressionReason(final.text, overlapIntent);
  const needsJudgement = !suppressionReason && overlapIntent === 'uncertain' && assistantSpeaking;
  const continuation = session.finalizationBuffer.drain();
  emitOmnixEvent(LIVE_STT_SPECULATION_FINAL_EVENT, {
    chatSessionId: final.chatSessionId,
    segmentId: final.segmentId,
    sourceSequence: final.sourceSequence,
    text: final.text,
  });
  dispatchLiveVoicePerfEvent({
    stage: 'stt_final_received',
    turnId: session.perfTurnId ?? `voice-turn:${Date.now()}`,
    timestamp: new Date().toISOString(),
    transcriptChars: final.text.trim().length,
    sttFinalizeMs: session.sttFinalRequestedAt === null ? undefined : Math.round(receivedAt - session.sttFinalRequestedAt),
    segmentId: final.segmentId,
    sourceSequence: final.sourceSequence,
    captureEpoch: final.captureEpoch,
  });
  session.reporter.record('stt_final_received', {
    ...currentLiveRuntimeProvenance(),
    chat_session_id: final.chatSessionId,
    stt_session_id: final.sttSessionId,
    capture_epoch: final.captureEpoch,
    segment_id: final.segmentId,
    result_id: final.resultId,
    finalize_request_id: final.finalizeRequestId,
    source_sequence: final.sourceSequence,
    start_sample: final.startSample,
    end_sample: final.endSample,
    protocol: final.protocol,
    transcript_chars: final.text.trim().length,
    stt_finalize_ms: session.sttFinalRequestedAt === null ? undefined : Math.round(receivedAt - session.sttFinalRequestedAt),
    overlap_intent: overlapIntent,
    overlap_confidence: finalOverlapAssessment?.confidence,
    overlap_reason: finalOverlapAssessment?.reason,
    interruption_dispatched: interruptionDispatched,
  }, 'live_voice_controller');
  resetTurnState(session);
  try {
    const judgedListening = needsJudgement && await overlapIsOnlyListening(session, card, final);
    if (suppressionReason || judgedListening) {
      const result = ignoredRoutingResult(final);
      session.reporter.record('coordination_completed', {
        segment_id: final.segmentId,
        result_id: final.resultId,
        source_sequence: final.sourceSequence,
        outcome: result.outcome,
        suppression_reason: suppressionReason ?? 'judged_listening',
        overlap_intent: overlapIntent,
        overlap_confidence: finalOverlapAssessment?.confidence,
        overlap_reason: finalOverlapAssessment?.reason,
      }, 'live_voice_controller');
      return result;
    }
    renderTranscript('You', final.text, 'final');
    session.reporter.record('coordination_started', {
      segment_id: final.segmentId,
      result_id: final.resultId,
      finalize_request_id: final.finalizeRequestId,
      source_sequence: final.sourceSequence,
      capture_epoch: final.captureEpoch,
      overlap_intent: overlapIntent,
      overlap_confidence: finalOverlapAssessment?.confidence,
      overlap_reason: finalOverlapAssessment?.reason,
      interruption_dispatched: interruptionDispatched,
    }, 'live_voice_controller');
    dispatchLiveVoicePerfEvent({
      stage: 'coordination_started',
      timestamp: new Date().toISOString(),
      segmentId: final.segmentId,
      sourceSequence: final.sourceSequence,
      captureEpoch: final.captureEpoch,
    });
    try {
      const result = await liveSessionCoordinator.routeAcceptedFinal(final);
      session.reporter.record('coordination_completed', {
        segment_id: final.segmentId,
        result_id: final.resultId,
        source_sequence: final.sourceSequence,
        outcome: result.outcome,
        task_contract_id: result.taskContractId,
        task_contract_version: result.taskContractVersion,
        error_code: result.errorCode,
      }, 'live_voice_controller');
      dispatchLiveVoicePerfEvent({
        stage: 'coordination_completed',
        timestamp: new Date().toISOString(),
        segmentId: final.segmentId,
        sourceSequence: final.sourceSequence,
        outcome: result.outcome,
        errorCode: result.errorCode,
      });
      if (result.outcome === 'failed') setPanelStatus(card, 'error');
      else setPanelStatus(card, 'connected');
      return result;
    } catch (error) {
      const result = failedRoutingResult(final, 'live_coordination_failed');
      session.reporter.record('coordination_completed', {
        segment_id: final.segmentId,
        result_id: final.resultId,
        source_sequence: final.sourceSequence,
        outcome: result.outcome,
        error_code: result.errorCode,
        error: error instanceof Error ? error.message : String(error),
      }, 'live_voice_controller');
      setPanelStatus(card, 'error');
      return result;
    }
  } finally {
    emitOmnixEvent(LIVE_STT_SPECULATION_DELIVERY_SETTLED_EVENT, {
      chatSessionId: final.chatSessionId,
      segmentId: final.segmentId,
      sourceSequence: final.sourceSequence,
      text: final.text,
    });
    replayFinalizationBuffer(session, continuation);
  }
}

/**
 * True when the reply should play on and the remark goes no further. A reply that ended while the model was deciding
 * is not cut off by anything, so the remark goes on as an ordinary turn, whatever the verdict: it may be an answer.
 */
async function overlapIsOnlyListening(
  session: LiveVoiceSession,
  card: HTMLElement,
  final: AcceptedVoiceFinal,
): Promise<boolean> {
  const startedAt = performance.now();
  emitOmnixEvent(ASSISTANT_AUDIO_DUCK_EVENT, { ducked: true, gain: JUDGING_GAIN, reason: 'overlap-judging', timestamp: startedAt });
  try {
    const verdict = await judgeOverlap(final.chatSessionId, final.text, currentAssistantSpeechText());
    if (controller.activeSession !== session) return true;
    const stillSpeaking = liveVoiceAssistantIsSpeaking();
    session.reporter.record('overlap_judged', {
      decision: verdict.decision,
      decided_by: verdict.source,
      reason: verdict.reason,
      elapsed_ms: Math.round(performance.now() - startedAt),
      transcript_chars: final.text.trim().length,
      still_speaking: stillSpeaking,
    }, 'live_voice_controller');
    if (!stillSpeaking) return false;
    const stop = verdict.decision === 'stop';
    dispatchLiveVoicePerfEvent({
      stage: 'overlap_classified',
      timestamp: new Date().toISOString(),
      intent: stop ? 'interrupt' : 'backchannel',
      confidence: verdict.source === 'model' ? 0.8 : 0.1,
      reason: verdict.reason ?? 'model_judged',
      transcriptChars: final.text.trim().length,
    });
    if (stop) dispatchAssistantVoiceInterrupt(card, 'interrupt', 0.8);
    return !stop;
  } finally {
    emitOmnixEvent(ASSISTANT_AUDIO_DUCK_EVENT, { ducked: false, gain: 1, reason: 'overlap-judged', timestamp: performance.now() });
  }
}

export function ignoredRoutingResult(final: AcceptedVoiceFinal): LiveFinalRoutingResult {
  const task = liveConversationStore.getState().coordination.taskContract;
  return { outcome: 'ignored', segmentId: final.segmentId, sourceSequence: final.sourceSequence, taskContractId: task.taskContractId, taskContractVersion: task.version };
}

export function failedRoutingResult(final: AcceptedVoiceFinal, errorCode: string): LiveFinalRoutingResult {
  const task = liveConversationStore.getState().coordination.taskContract;
  return { outcome: 'failed', segmentId: final.segmentId, sourceSequence: final.sourceSequence, taskContractId: task.taskContractId, taskContractVersion: task.version, errorCode };
}
