import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { updateLiveConversationSettings } from './live-voice-conversation-settings';
import {
  assessCallerVoice,
  callerVoiceFromSimilarity,
  clearHeldFinals,
  holdFinalForCaller,
  LiveSpeakerScores,
  MIN_SCORED_SEGMENT_SAMPLES,
  onlyRespondToMeActive,
  PROVISIONAL_CALLER_THRESHOLD,
  sendHeldFinal,
} from './live-voice-speaker-gate';
import { liveVoiceTranscriptStore } from './live-voice-transcript-store';

const longFinal = { segmentId: 'segment', sourceSequence: 3, startSample: 0, endSample: MIN_SCORED_SEGMENT_SAMPLES };

beforeEach(() => {
  window.localStorage.clear();
  liveVoiceTranscriptStore.resetForTests();
  clearHeldFinals();
});

afterEach(() => {
  vi.useRealTimers();
  window.localStorage.clear();
});

describe('the call\'s speaker scores', () => {
  it('hands a waiting final its score as soon as it comes', async () => {
    const scores = new LiveSpeakerScores();
    scores.setAvailable(true);

    const waiting = scores.waitFor('segment', 3, 300);
    scores.record('segment', 3, 0.72);

    await expect(waiting).resolves.toBe(0.72);
    // A score already in is answered at once.
    await expect(scores.waitFor('segment', 3, 300)).resolves.toBe(0.72);
  });

  it('gives up after the wait, and never waits on a connection that does not score', async () => {
    vi.useFakeTimers();
    const scores = new LiveSpeakerScores();
    scores.setAvailable(true);

    const waiting = scores.waitFor('segment', 3, 300);
    vi.advanceTimersByTime(300);
    await expect(waiting).resolves.toBeNull();

    scores.setAvailable(false);
    await expect(scores.waitFor('segment', 4, 300)).resolves.toBeNull();
  });

  it('a new call releases what the last one was waiting for, and forgets its scores', async () => {
    const scores = new LiveSpeakerScores();
    scores.setAvailable(true);
    scores.record('segment', 1, 0.9);
    const waiting = scores.waitFor('segment', 2, 10_000);

    scores.reset();

    await expect(waiting).resolves.toBeNull();
    expect(scores.isAvailable).toBe(false);
    await expect(scores.waitFor('segment', 1, 0)).resolves.toBeNull();
  });

  it('keeps only the latest scores', async () => {
    const scores = new LiveSpeakerScores();
    for (let sequence = 0; sequence < 40; sequence += 1) scores.record('segment', sequence, 0.5);

    await expect(scores.waitFor('segment', 0, 0)).resolves.toBeNull();
    await expect(scores.waitFor('segment', 39, 0)).resolves.toBe(0.5);
  });
});

describe('whose voice a final is', () => {
  it('reads the score against the threshold; no score is no verdict', () => {
    expect(callerVoiceFromSimilarity(PROVISIONAL_CALLER_THRESHOLD)).toBe('caller');
    expect(callerVoiceFromSimilarity(0.1)).toBe('other');
    expect(callerVoiceFromSimilarity(null)).toBe('unknown');
    expect(callerVoiceFromSimilarity(Number.NaN)).toBe('unknown');
  });

  it('asks nothing while "Only respond to me" is off, or the call does not score', async () => {
    const scores = new LiveSpeakerScores();
    scores.setAvailable(true);
    expect(onlyRespondToMeActive(scores)).toBe(false);
    await expect(assessCallerVoice(longFinal, { scores })).resolves.toMatchObject({ verdict: 'unknown', basis: 'off' });

    updateLiveConversationSettings({ onlyRespondToMe: true });
    scores.setAvailable(false);
    expect(onlyRespondToMeActive(scores)).toBe(false);
  });

  it('has no verdict on a segment too short to score', async () => {
    updateLiveConversationSettings({ onlyRespondToMe: true });
    const scores = new LiveSpeakerScores();
    scores.setAvailable(true);

    const assessment = await assessCallerVoice({ ...longFinal, endSample: MIN_SCORED_SEGMENT_SAMPLES - 1 }, { scores });

    expect(assessment).toMatchObject({ verdict: 'unknown', basis: 'short_segment', waitedMs: 0 });
  });

  it('waits for the score of a long segment, and says another voice is another voice', async () => {
    updateLiveConversationSettings({ onlyRespondToMe: true });
    const scores = new LiveSpeakerScores();
    scores.setAvailable(true);

    const assessing = assessCallerVoice(longFinal, { scores, waitMs: 1_000 });
    scores.record('segment', 3, 0.05);

    await expect(assessing).resolves.toMatchObject({ verdict: 'other', similarity: 0.05, basis: 'scored' });
  });

  it('takes a null score (the service could not say) as no verdict', async () => {
    updateLiveConversationSettings({ onlyRespondToMe: true });
    const scores = new LiveSpeakerScores();
    scores.setAvailable(true);
    scores.record('segment', 3, null);

    await expect(assessCallerVoice(longFinal, { scores })).resolves.toMatchObject({ verdict: 'unknown', basis: 'no_score' });
  });
});

describe('a held final', () => {
  it('shows greyed and goes on as the caller\'s turn on "Send anyway", once', async () => {
    const send = vi.fn(async () => undefined);
    const rowId = holdFinalForCaller('What time is the match?', send);

    expect(liveVoiceTranscriptStore.getState().rows).toEqual([expect.objectContaining({ id: rowId, held: 'pending' })]);
    await expect(sendHeldFinal(rowId!)).resolves.toBe(true);
    await expect(sendHeldFinal(rowId!)).resolves.toBe(false);

    expect(send).toHaveBeenCalledOnce();
    expect(liveVoiceTranscriptStore.getState().rows[0]?.held).toBeUndefined();
  });

  it('cannot be sent once its call has ended', async () => {
    const send = vi.fn(async () => undefined);
    const rowId = holdFinalForCaller('Turn it up.', send);

    clearHeldFinals();

    await expect(sendHeldFinal(rowId!)).resolves.toBe(false);
    expect(send).not.toHaveBeenCalled();
    expect(liveVoiceTranscriptStore.getState().rows[0]).toMatchObject({ text: 'Turn it up.', held: 'expired' });
  });
});
