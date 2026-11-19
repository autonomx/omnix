/**
 * "Only respond to me" (companion 2.4): a final in another voice is held instead of becoming a turn.
 *
 * The speech service scores each final of 0.8 s or more against the caller's voiceprint and sends the score just after
 * the final. With the setting on, and only on a connection that said it scores (`session_ready.speakerScores`), a final
 * waits up to `SPEAKER_SCORE_WAIT_MS` for its score. A score under the threshold holds the final: it is shown greyed
 * with "Send anyway", its speculation is dropped, and speech over a reply in that voice never stops the reply. No print,
 * a short segment, a null score or one that comes too late all mean today's behaviour. The setting is off by default.
 */
import { readLiveConversationSettings } from './live-voice-conversation-settings';
import { liveVoiceTranscriptStore } from './live-voice-transcript-store';

/**
 * Provisional: TitaNet puts one person's short segments well above this and other voices well below it. The owner's
 * labelled recordings (2.3, `scripts/voiceprint_threshold_eval.py`) replace it before the setting may default on.
 */
export const PROVISIONAL_CALLER_THRESHOLD = 0.35;
/** How long a final waits for its score; an embedding on the speech service takes tens of milliseconds. */
export const SPEAKER_SCORE_WAIT_MS = 300;
/** The service scores nothing shorter (`MIN_SCORED_SEGMENT_SECONDS`, 0.8 s at 16 kHz). */
export const MIN_SCORED_SEGMENT_SAMPLES = 12_800;
const MAX_REMEMBERED_SCORES = 32;

export type CallerVoiceVerdict = 'caller' | 'other' | 'unknown';

type ScoredSegment = { segmentId: string; sourceSequence: number; startSample: number; endSample: number };
type Waiter = (similarity: number | null) => void;

const key = (segmentId: string, sequence: number) => `${segmentId}#${sequence}`;

/** The call's speaker scores by segment, and the finals waiting for theirs. One call at a time. */
export class LiveSpeakerScores {
  private available = false;
  private readonly scores = new Map<string, number | null>();
  private readonly waiters = new Map<string, Set<Waiter>>();

  get isAvailable(): boolean {
    return this.available;
  }

  setAvailable(available: boolean): void {
    this.available = available;
    if (!available) this.releaseWaiters();
  }

  record(segmentId: string, sequence: number, similarity: number | null): void {
    const id = key(segmentId, sequence);
    this.scores.set(id, similarity);
    while (this.scores.size > MAX_REMEMBERED_SCORES) {
      const oldest = this.scores.keys().next().value;
      if (typeof oldest !== 'string') break;
      this.scores.delete(oldest);
    }
    this.waiters.get(id)?.forEach((resolve) => resolve(similarity));
    this.waiters.delete(id);
  }

  /** The segment's score, or null when it has none within `timeoutMs`. */
  waitFor(segmentId: string, sequence: number, timeoutMs: number): Promise<number | null> {
    const id = key(segmentId, sequence);
    if (this.scores.has(id)) return Promise.resolve(this.scores.get(id) ?? null);
    if (!this.available) return Promise.resolve(null);
    return new Promise((resolve) => {
      const waiters = this.waiters.get(id) ?? new Set<Waiter>();
      const done: Waiter = (similarity) => {
        clearTimeout(timer);
        waiters.delete(done);
        resolve(similarity);
      };
      const timer = setTimeout(() => done(null), timeoutMs);
      waiters.add(done);
      this.waiters.set(id, waiters);
    });
  }

  reset(): void {
    this.available = false;
    this.scores.clear();
    this.releaseWaiters();
  }

  private releaseWaiters(): void {
    const pending = [...this.waiters.values()].flatMap((waiters) => [...waiters]);
    this.waiters.clear();
    pending.forEach((resolve) => resolve(null));
  }
}

export const liveSpeakerScores = new LiveSpeakerScores();

/** The setting is on and this call's speech service scores voices. */
export function onlyRespondToMeActive(scores: LiveSpeakerScores = liveSpeakerScores): boolean {
  return readLiveConversationSettings().onlyRespondToMe && scores.isAvailable;
}

export function callerVoiceFromSimilarity(
  similarity: number | null,
  threshold: number = PROVISIONAL_CALLER_THRESHOLD,
): CallerVoiceVerdict {
  if (similarity === null || !Number.isFinite(similarity)) return 'unknown';
  return similarity >= threshold ? 'caller' : 'other';
}

export type CallerVoiceAssessment = {
  verdict: CallerVoiceVerdict;
  similarity: number | null;
  /** Why there is no verdict, or `scored`. */
  basis: 'off' | 'short_segment' | 'no_score' | 'scored';
  waitedMs: number;
};

/** Whose voice the final is, waiting briefly for its score; `unknown` whenever there is nothing to go on. */
export async function assessCallerVoice(
  final: ScoredSegment,
  { scores = liveSpeakerScores, waitMs = SPEAKER_SCORE_WAIT_MS }: { scores?: LiveSpeakerScores; waitMs?: number } = {},
): Promise<CallerVoiceAssessment> {
  if (!onlyRespondToMeActive(scores)) return { verdict: 'unknown', similarity: null, basis: 'off', waitedMs: 0 };
  if (final.endSample - final.startSample < MIN_SCORED_SEGMENT_SAMPLES) {
    return { verdict: 'unknown', similarity: null, basis: 'short_segment', waitedMs: 0 };
  }
  const startedAt = performance.now();
  const similarity = await scores.waitFor(final.segmentId, final.sourceSequence, waitMs);
  const waitedMs = Math.round(performance.now() - startedAt);
  return {
    verdict: callerVoiceFromSimilarity(similarity),
    similarity,
    basis: similarity === null ? 'no_score' : 'scored',
    waitedMs,
  };
}

const heldFinals = new Map<string, () => Promise<void>>();

/**
 * Holds a final in another voice: its words stay in the transcript, greyed, with "Send anyway". Returns the row's id.
 * The row is the speaker's draft settled, so the partials of that turn do not linger beside it.
 */
export function holdFinalForCaller(text: string, sendAnyway: () => Promise<void>): string | null {
  const rowId = liveVoiceTranscriptStore.writeHeld(text);
  if (rowId) heldFinals.set(rowId, sendAnyway);
  return rowId;
}

/** "Send anyway": the held final goes on as the caller's turn. False when it is no longer held. */
export async function sendHeldFinal(rowId: string): Promise<boolean> {
  const send = heldFinals.get(rowId);
  if (!send) {
    liveVoiceTranscriptStore.expireHeld();
    return false;
  }
  heldFinals.delete(rowId);
  liveVoiceTranscriptStore.releaseHeld(rowId);
  await send();
  return true;
}

/** The call ended: nothing it held can be sent from another call, so the rows lose their button. */
export function clearHeldFinals(): void {
  heldFinals.clear();
  liveVoiceTranscriptStore.expireHeld();
}
