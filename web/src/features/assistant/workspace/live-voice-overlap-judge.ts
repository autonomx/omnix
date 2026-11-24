/** Asks the call's model whether a short remark over the assistant's speech should stop it. */
import { pipelineFetch } from '../../../api/fetchPipeline';
import { createApi } from '../api/gateway';
import { reportLiveCallFailure } from './live-call-health';

export type OverlapVerdict = {
  decision: 'stop' | 'continue';
  /** `proposal_answer`: a confirm or cancel said over the call's question about a proposal, decided by code. */
  source: 'model' | 'fallback' | 'proposal_answer';
  reason: string | null;
};

const CALL_ID_HEADER = 'X-Omnix-Call-Id';
// A little past the server's own deadline for the model, for a request stuck on its way.
const REQUEST_DEADLINE_MS = 1_500;
const MAX_TRANSCRIPT_CHARS = 400;
const MAX_ASSISTANT_CHARS = 600;

/** Whatever goes wrong, the answer is to keep playing: a missed interruption costs less than a reply cut off. */
export async function judgeOverlap(
  sessionId: string,
  transcript: string,
  assistantText: string,
  fetchImpl: typeof fetch = pipelineFetch,
  { proposalAnswerOnly = false }: { proposalAnswerOnly?: boolean } = {},
): Promise<OverlapVerdict> {
  const abort = new AbortController();
  const deadline = setTimeout(() => abort.abort(), REQUEST_DEADLINE_MS);
  try {
    const { data, response } = await createApi({ fetchImpl }).POST('/api/live-call/sessions/{session_id}/overlap-judgement', {
      params: { path: { session_id: sessionId } },
      body: {
        transcript: transcript.trim().slice(0, MAX_TRANSCRIPT_CHARS),
        assistant_text: assistantText.trim().slice(-MAX_ASSISTANT_CHARS),
        ...(proposalAnswerOnly ? { proposal_answer_only: true } : {}),
      },
      // The model's waiting process is on the call's replica.
      headers: { [CALL_ID_HEADER]: encodeURIComponent(sessionId) },
      signal: abort.signal,
    });
    if (!data) {
      reportLiveCallFailure('overlap_judgement', { status: response.status });
      return fallback('request_refused');
    }
    return { decision: data.decision, source: data.source, reason: data.reason ?? null };
  } catch (error) {
    reportLiveCallFailure('overlap_judgement');
    return fallback(abort.signal.aborted ? 'request_deadline' : error instanceof Error ? error.name : 'request_failed');
  } finally {
    clearTimeout(deadline);
  }
}

function fallback(reason: string): OverlapVerdict {
  return { decision: 'continue', source: 'fallback', reason };
}
