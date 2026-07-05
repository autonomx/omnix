import {
  createLiveCallDiagnosticsReporter,
  createLiveCallTraceId,
  type LiveCallDiagnosticsReporter,
} from './live-call-diagnostics-client';
import {
  createLiveVoicePcmSession,
  type LiveVoicePcmSession,
} from './live-voice-pcm-session';

export type LiveVoiceTurnAudio = {
  traceId: string;
  recordTextChunk: (text: string) => void;
  enqueuePhrase: (text: string, reason: string) => Promise<void>;
  finish: () => Promise<void>;
  stop: (reason?: string) => Promise<void>;
};

export async function createLiveVoiceTurnAudio(
  sessionId: string,
  voiceId: string | null,
): Promise<LiveVoiceTurnAudio> {
  const traceId = createLiveCallTraceId(sessionId);
  const reporter = createLiveCallDiagnosticsReporter(traceId);
  const startedAtMs = performance.now();
  const session = await createLiveVoicePcmSession(traceId, voiceId, reporter);
  let phraseCount = 0;
  let textChunkCount = 0;
  let closed = false;

  reporter.record('turn_started_direct', {
    session_id: sessionId,
    voice_id: voiceId,
  }, 'controller');

  const recordTextChunk = (text: string): void => {
    if (closed) return;
    reporter.record('llm_text_chunk_received', {
      text_chunk_index: textChunkCount,
      text,
      text_length: text.length,
      elapsed_ms: performance.now() - startedAtMs,
    }, 'controller');
    textChunkCount += 1;
  };

  const enqueuePhrase = async (text: string, reason: string): Promise<void> => {
    const phrase = text.trim();
    if (!phrase || closed) return;
    const phraseIndex = phraseCount;
    phraseCount += 1;
    reporter.record('phrase_queued', {
      phrase_index: phraseIndex,
      reason,
      text: phrase,
      text_length: phrase.length,
      elapsed_ms: performance.now() - startedAtMs,
    }, 'controller');
    await session.enqueuePhrase(phrase, phraseIndex);
  };

  const closeReporter = async (
    event: string,
    details: Record<string, unknown> = {},
  ): Promise<void> => {
    await reporter.close(event, {
      elapsed_ms: performance.now() - startedAtMs,
      text_chunks: textChunkCount,
      phrases: phraseCount,
      ...details,
    });
  };

  const finish = async (): Promise<void> => {
    if (closed) return;
    closed = true;
    reporter.record('llm_stream_finished', {
      elapsed_ms: performance.now() - startedAtMs,
      text_chunks: textChunkCount,
      phrases: phraseCount,
    }, 'controller');
    try {
      await session.finish();
      await closeReporter('turn_finished');
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      await session.stop('turn-finish-failed');
      await closeReporter('turn_failed', { error: message });
      throw error;
    }
  };

  const stop = async (reason = 'stopped'): Promise<void> => {
    if (closed) return;
    closed = true;
    reporter.record('turn_stop_requested', {
      reason,
      elapsed_ms: performance.now() - startedAtMs,
      text_chunks: textChunkCount,
      phrases: phraseCount,
    }, 'controller');
    await session.stop(reason);
    await closeReporter('turn_stopped', { reason });
  };

  return { traceId, recordTextChunk, enqueuePhrase, finish, stop };
}

export function liveVoiceTurnLogContext(
  turn: LiveVoiceTurnAudio | null,
  reporter?: LiveCallDiagnosticsReporter,
  session?: LiveVoicePcmSession,
): Record<string, unknown> {
  return {
    trace_id: turn?.traceId ?? reporter?.traceId ?? null,
    session_closed: session?.isClosed() ?? null,
  };
}
