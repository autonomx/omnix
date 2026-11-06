import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ASSISTANT_AUDIO_DUCK_EVENT, ASSISTANT_VOICE_INTERRUPT_EVENT } from '../../../events/bus';
import type { AcceptedVoiceFinal } from './live-accepted-final';
import { liveConversationStore } from './live-conversation-store';
import { controller, type LiveVoiceSession } from './live-voice-controller-state';
import { handleAcceptedFinal } from './live-voice-final-routing';
import { judgeOverlap, type OverlapVerdict } from './live-voice-overlap-judge';
import { liveSessionCoordinator } from './live-session-coordinator';

vi.mock('./live-voice-overlap-judge', () => ({ judgeOverlap: vi.fn() }));
vi.mock('./live-voice-session-lifecycle', () => ({ resetTurnState: vi.fn(), stopLiveVoice: vi.fn() }));

const judge = vi.mocked(judgeOverlap);
const card = document.createElement('div');
let routed: ReturnType<typeof vi.spyOn>;
let interrupts: number;
let gains: number[];
let records: Array<[string, Record<string, unknown>]>;
const countInterrupt = () => { interrupts += 1; };
const recordGain = (event: Event) => { gains.push((event as CustomEvent<{ gain: number }>).detail.gain); };

function final(text: string): AcceptedVoiceFinal {
  return { chatSessionId: 'chat:one', text, segmentId: 'segment', sourceSequence: 1, resultId: 'result' } as unknown as AcceptedVoiceFinal;
}

function startSession(overlapIntent: LiveVoiceSession['overlapIntent']): void {
  controller.activeSession = {
    card,
    overlapIntent,
    interruptionDispatched: false,
    perfTurnId: 'turn',
    sttFinalRequestedAt: null,
    finalizationBuffer: { drain: () => [] },
    reporter: { record: (name: string, fields: Record<string, unknown>) => { records.push([name, fields]); } },
  } as unknown as LiveVoiceSession;
}

function assistantSpeaks(speaking: boolean): void {
  liveConversationStore.dispatch({ type: 'conversation', event: { type: 'assistant_turn', value: speaking ? 'speaking' : 'idle' } });
}

function resolved(verdict: OverlapVerdict) {
  judge.mockResolvedValue(verdict);
}

beforeEach(() => {
  interrupts = 0;
  gains = [];
  records = [];
  judge.mockReset();
  liveConversationStore.reset();
  routed = vi.spyOn(liveSessionCoordinator, 'routeAcceptedFinal').mockResolvedValue({
    outcome: 'conversation_submitted', segmentId: 'segment', sourceSequence: 1, taskContractId: 'task', taskContractVersion: 1,
  } as never);
  window.addEventListener(ASSISTANT_VOICE_INTERRUPT_EVENT, countInterrupt);
  window.addEventListener(ASSISTANT_AUDIO_DUCK_EVENT, recordGain);
});

afterEach(() => {
  routed.mockRestore();
  window.removeEventListener(ASSISTANT_VOICE_INTERRUPT_EVENT, countInterrupt);
  window.removeEventListener(ASSISTANT_AUDIO_DUCK_EVENT, recordGain);
  controller.activeSession = null;
  liveConversationStore.reset();
});

describe('a short remark over the assistant', () => {
  // Real: "Cool." opened over a reply, and "Uh" just before its audio started. Both used to cut it off.
  it.each([['uncertain' as const, 'Cool.'], [null, 'Uh']])('keeps the reply playing when judged listening (%s, %s)', async (intent, text) => {
    startSession(intent);
    assistantSpeaks(true);
    resolved({ decision: 'continue', source: 'model', reason: null });

    const result = await handleAcceptedFinal(card, final(text));

    expect(judge).toHaveBeenCalledOnce();
    expect(result.outcome).toBe('ignored');
    expect(routed).not.toHaveBeenCalled();
    expect(interrupts).toBe(0);
    expect(gains).toEqual([0.18, 1]);
  });

  it('stops the reply and becomes a turn when judged to want the floor', async () => {
    startSession('uncertain');
    assistantSpeaks(true);
    resolved({ decision: 'stop', source: 'model', reason: null });

    const result = await handleAcceptedFinal(card, final('Hang on.'));

    expect(interrupts).toBe(1);
    expect(routed).toHaveBeenCalledOnce();
    expect(result.outcome).toBe('conversation_submitted');
    expect(gains[0]).toBe(0.18);
    expect(gains.at(-1)).toBe(1); // ready for the next reply
  });

  it('keeps the reply playing when the model could not say', async () => {
    startSession('uncertain');
    assistantSpeaks(true);
    resolved({ decision: 'continue', source: 'fallback', reason: 'deadline' });

    await handleAcceptedFinal(card, final('Hang on.'));

    expect(routed).not.toHaveBeenCalled();
    expect(interrupts).toBe(0);
    expect(records.find(([name]) => name === 'overlap_judged')?.[1]).toMatchObject({ decided_by: 'fallback', reason: 'deadline' });
  });

  it('becomes an ordinary turn when the reply ended while the model was deciding', async () => {
    startSession('uncertain');
    assistantSpeaks(true);
    judge.mockImplementation(async () => {
      assistantSpeaks(false);
      return { decision: 'continue', source: 'model', reason: null };
    });

    await handleAcceptedFinal(card, final('Pizza, mostly.'));

    expect(routed).toHaveBeenCalledOnce();
    expect(interrupts).toBe(0);
  });

  it('goes nowhere when the call ended while the model was deciding', async () => {
    startSession('uncertain');
    assistantSpeaks(true);
    judge.mockImplementation(async () => {
      controller.activeSession = null;
      return { decision: 'stop', source: 'model', reason: null };
    });

    const result = await handleAcceptedFinal(card, final('Hang on.'));

    expect(result.outcome).toBe('ignored');
    expect(routed).not.toHaveBeenCalled();
    expect(interrupts).toBe(0);
  });
});

describe('what needs no judging', () => {
  it('does not ask about a remark while the assistant is silent', async () => {
    startSession(null);
    assistantSpeaks(false);

    await handleAcceptedFinal(card, final('Cool.'));

    expect(judge).not.toHaveBeenCalled();
    expect(routed).toHaveBeenCalledOnce();
  });

  it('does not ask about a sentence over the reply', async () => {
    startSession('uncertain');
    assistantSpeaks(true);

    await handleAcceptedFinal(card, final("I don't have to explain anything."));

    expect(judge).not.toHaveBeenCalled();
    expect(interrupts).toBe(1);
    expect(routed).toHaveBeenCalledOnce();
  });

  it('does not ask about an empty transcript', async () => {
    startSession('uncertain');
    assistantSpeaks(true);

    const result = await handleAcceptedFinal(card, final('   '));

    expect(judge).not.toHaveBeenCalled();
    expect(result.outcome).toBe('ignored');
  });
});
