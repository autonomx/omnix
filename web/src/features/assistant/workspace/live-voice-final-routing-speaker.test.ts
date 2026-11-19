import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  ASSISTANT_AUDIO_DUCK_EVENT,
  ASSISTANT_VOICE_INTERRUPT_EVENT,
  LIVE_STT_SPECULATION_DELIVERY_SETTLED_EVENT,
  LIVE_STT_SPECULATION_FINAL_EVENT,
} from '../../../events/bus';
import type { AcceptedVoiceFinal } from './live-accepted-final';
import { liveConversationStore } from './live-conversation-store';
import { liveSessionCoordinator } from './live-session-coordinator';
import { controller, type LiveVoiceSession } from './live-voice-controller-state';
import { updateLiveConversationSettings } from './live-voice-conversation-settings';
import { handleAcceptedFinal } from './live-voice-final-routing';
import { clearHeldFinals, liveSpeakerScores, MIN_SCORED_SEGMENT_SAMPLES, sendHeldFinal } from './live-voice-speaker-gate';
import { liveVoiceTranscriptStore } from './live-voice-transcript-store';

vi.mock('./live-voice-overlap-judge', () => ({ judgeOverlap: vi.fn() }));
vi.mock('./live-voice-session-lifecycle', () => ({ resetTurnState: vi.fn(), stopLiveVoice: vi.fn() }));

const card = document.createElement('div');
let routed: ReturnType<typeof vi.spyOn>;
let events: Array<[string, Record<string, unknown>]>;
let records: Array<[string, Record<string, unknown>]>;
const WATCHED = [ASSISTANT_VOICE_INTERRUPT_EVENT, ASSISTANT_AUDIO_DUCK_EVENT, LIVE_STT_SPECULATION_FINAL_EVENT, LIVE_STT_SPECULATION_DELIVERY_SETTLED_EVENT];
const watch = (event: Event) => { events.push([event.type, (event as CustomEvent).detail]); };
const named = (type: string) => events.filter(([name]) => name === type).map(([, detail]) => detail);

function final(text: string, samples = MIN_SCORED_SEGMENT_SAMPLES * 2): AcceptedVoiceFinal {
  return {
    chatSessionId: 'chat:one', text, segmentId: 'segment', sourceSequence: 7, resultId: 'result', startSample: 0, endSample: samples,
  } as unknown as AcceptedVoiceFinal;
}

/** A call whose partials confirmed an interruption over the reply, held for the final's voice. */
function startSession({ deferred = false } = {}): LiveVoiceSession {
  const session = {
    card,
    overlapIntent: deferred ? 'interrupt' : null,
    interruptionDispatched: deferred,
    deferredInterrupt: deferred ? { intent: 'interrupt', confidence: 0.9, unduckTimer: setTimeout(() => undefined, 60_000) } : null,
    perfTurnId: 'turn',
    sttFinalRequestedAt: null,
    finalResponseTimer: null,
    finalizationBuffer: { drain: () => [] },
    reporter: { record: (name: string, fields: Record<string, unknown>) => { records.push([name, fields]); } },
  } as unknown as LiveVoiceSession;
  controller.activeSession = session;
  return session;
}

function assistantSpeaks(speaking: boolean): void {
  liveConversationStore.dispatch({ type: 'conversation', event: { type: 'assistant_turn', value: speaking ? 'speaking' : 'idle' } });
}

beforeEach(() => {
  events = [];
  records = [];
  window.localStorage.clear();
  liveConversationStore.reset();
  liveVoiceTranscriptStore.resetForTests();
  liveSpeakerScores.reset();
  clearHeldFinals();
  updateLiveConversationSettings({ onlyRespondToMe: true });
  liveSpeakerScores.setAvailable(true);
  routed = vi.spyOn(liveSessionCoordinator, 'routeAcceptedFinal').mockResolvedValue({
    outcome: 'conversation_submitted', segmentId: 'segment', sourceSequence: 7, taskContractId: 'task', taskContractVersion: 1,
  } as never);
  WATCHED.forEach((type) => window.addEventListener(type, watch));
});

afterEach(() => {
  routed.mockRestore();
  WATCHED.forEach((type) => window.removeEventListener(type, watch));
  controller.activeSession = null;
  liveConversationStore.reset();
  liveSpeakerScores.reset();
  window.localStorage.clear();
});

describe('"Only respond to me": a final in another voice', () => {
  it('is held, not answered: greyed in the transcript, its speculation dropped, the reply left playing', async () => {
    const session = startSession({ deferred: true });
    assistantSpeaks(true);
    liveSpeakerScores.record('segment', 7, 0.04);

    const result = await handleAcceptedFinal(card, final('And the score is two nil.'));

    expect(result.outcome).toBe('ignored');
    expect(routed).not.toHaveBeenCalled();
    expect(named(ASSISTANT_VOICE_INTERRUPT_EVENT)).toEqual([]);
    expect(named(LIVE_STT_SPECULATION_FINAL_EVENT)).toEqual([]);
    expect(named(LIVE_STT_SPECULATION_DELIVERY_SETTLED_EVENT)).toHaveLength(1);
    expect(named(ASSISTANT_AUDIO_DUCK_EVENT).at(-1)).toMatchObject({ gain: 1 });
    expect(session.deferredInterrupt).toBeNull();
    expect(liveVoiceTranscriptStore.getState().rows).toEqual([
      expect.objectContaining({ speaker: 'You', text: 'And the score is two nil.', held: 'pending' }),
    ]);
    expect(records.find(([name]) => name === 'speaker_assessed')?.[1]).toMatchObject({ verdict: 'other', basis: 'scored', similarity: 0.04 });
    expect(records.find(([name]) => name === 'coordination_completed')?.[1]).toMatchObject({ suppression_reason: 'other_voice' });
  });

  it('goes on as the caller\'s turn on "Send anyway"', async () => {
    startSession();
    liveSpeakerScores.record('segment', 7, 0.04);
    await handleAcceptedFinal(card, final('Remind me to call Sam.'));
    const rowId = liveVoiceTranscriptStore.getState().rows[0]!.id;

    await expect(sendHeldFinal(rowId)).resolves.toBe(true);

    expect(routed).toHaveBeenCalledOnce();
    expect(records.some(([name]) => name === 'held_final_sent_anyway')).toBe(true);
    expect(liveVoiceTranscriptStore.getState().rows[0]?.held).toBeUndefined();
  });
});

describe('"Only respond to me": a final in the caller\'s voice, or with no verdict', () => {
  it.each([
    ['the caller\'s voice', 0.81 as number | null],
    ['a null score', null],
  ])('becomes a turn and makes the interruption it held (%s)', async (_label, similarity) => {
    startSession({ deferred: true });
    assistantSpeaks(true);
    liveSpeakerScores.record('segment', 7, similarity);

    const result = await handleAcceptedFinal(card, final('Wait, which one?'));

    expect(result.outcome).toBe('conversation_submitted');
    expect(routed).toHaveBeenCalledOnce();
    expect(named(ASSISTANT_VOICE_INTERRUPT_EVENT)).toEqual([expect.objectContaining({ source: 'live-voice', intent: 'interrupt' })]);
    expect(named(ASSISTANT_AUDIO_DUCK_EVENT).at(-1)).toMatchObject({ gain: 1 });
    expect(named(LIVE_STT_SPECULATION_FINAL_EVENT)).toHaveLength(1);
  });

  it('does not wait for a score on a segment too short to have one', async () => {
    startSession();

    const result = await handleAcceptedFinal(card, final('Yes.', MIN_SCORED_SEGMENT_SAMPLES - 1));

    expect(result.outcome).toBe('conversation_submitted');
    expect(records.find(([name]) => name === 'speaker_assessed')?.[1]).toMatchObject({ basis: 'short_segment', waited_ms: 0 });
  });

  it('cancels a reply not yet audible, which the speech alone no longer did', async () => {
    startSession();
    liveConversationStore.dispatch({ type: 'conversation', event: { type: 'connection', value: 'connected' } });
    liveConversationStore.dispatch({ type: 'conversation', event: { type: 'assistant_turn', value: 'generating' } });
    liveSpeakerScores.record('segment', 7, 0.9);

    await handleAcceptedFinal(card, final('Actually, never mind that.'));

    expect(named(ASSISTANT_VOICE_INTERRUPT_EVENT)).toEqual([
      expect.objectContaining({ source: 'pending-output-user-speech', reason: 'caller_final_before_audio_started' }),
    ]);
  });
});

describe('with "Only respond to me" off', () => {
  it('routes every final as today and records no assessment', async () => {
    updateLiveConversationSettings({ onlyRespondToMe: false });
    startSession();
    liveSpeakerScores.record('segment', 7, 0.01);

    const result = await handleAcceptedFinal(card, final('Who is that on the TV?'));

    expect(result.outcome).toBe('conversation_submitted');
    expect(records.some(([name]) => name === 'speaker_assessed')).toBe(false);
  });
});
