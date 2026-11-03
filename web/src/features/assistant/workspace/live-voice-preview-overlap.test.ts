import { afterEach, describe, expect, it, vi } from 'vitest';

import { ASSISTANT_VOICE_INTERRUPT_EVENT } from '../../../events/bus';
import { acceptedFinalSuppressionReason } from './live-accepted-final-routing';
import { assessFinalOverlap, interruptOnFinalOverlap, overlapAwaitsInterruption } from './live-voice-preview';

const hardStop = { intent: 'hard_stop', confidence: 0.99, reason: 'explicit_stop' } as const;

function interrupts(): { events: unknown[]; stop: () => void } {
  const events: unknown[] = [];
  const listener = (event: Event) => events.push((event as CustomEvent).detail);
  window.addEventListener(ASSISTANT_VOICE_INTERRUPT_EVENT, listener);
  return { events, stop: () => window.removeEventListener(ASSISTANT_VOICE_INTERRUPT_EVENT, listener) };
}

describe('a spoken stop over the assistant', () => {
  afterEach(() => vi.restoreAllMocks());

  it('is assessed in any floor state until it has interrupted: a one-word stop pauses before its partial', () => {
    expect(overlapAwaitsInterruption({ overlapIntent: 'uncertain', interruptionDispatched: false })).toBe(true);
    expect(overlapAwaitsInterruption({ overlapIntent: 'backchannel', interruptionDispatched: false })).toBe(true);
    expect(overlapAwaitsInterruption({ overlapIntent: 'hard_stop', interruptionDispatched: true })).toBe(false);
    // Speech that did not start over the assistant is never an overlap.
    expect(overlapAwaitsInterruption({ overlapIntent: null, interruptionDispatched: false })).toBe(false);
  });

  it('interrupts on its final transcript when the partials did not, once, while the assistant speaks', () => {
    const watch = interrupts();
    const session = { card: document.createElement('section'), interruptionDispatched: false };

    interruptOnFinalOverlap(session, hardStop, true);
    interruptOnFinalOverlap(session, hardStop, true);

    expect(session.interruptionDispatched).toBe(true);
    expect(watch.events).toEqual([expect.objectContaining({ source: 'live-voice', intent: 'hard_stop' })]);
    watch.stop();
  });

  it('leaves a finished reply, a backchannel and an unassessed final alone', () => {
    const watch = interrupts();
    const card = document.createElement('section');

    interruptOnFinalOverlap({ card, interruptionDispatched: false }, hardStop, false);
    interruptOnFinalOverlap({ card, interruptionDispatched: false },
      { intent: 'backchannel', confidence: 0.9, reason: 'acknowledgement' }, true);
    interruptOnFinalOverlap({ card, interruptionDispatched: false }, null, true);

    expect(watch.events).toEqual([]);
    watch.stop();
  });
});

describe('the final transcript of a turn that began over the assistant', () => {
  it('is judged on all its words, not on what its first partial said', () => {
    // "Yeah" alone is a backchannel; the sentence it started is not, and must reach the conversation.
    const sentence = assessFinalOverlap('backchannel', 'Yeah, how is the release going?');
    expect(sentence?.intent).toBe('interrupt');
    expect(acceptedFinalSuppressionReason('Yeah, how is the release going?', sentence?.intent ?? null)).toBeNull();
    expect(assessFinalOverlap('hard_stop', 'No, I meant the other farm')?.intent).toBe('interrupt');
    expect(assessFinalOverlap('noise', 'tell me about the mango harvest this year')?.intent).toBe('interrupt');
    expect(assessFinalOverlap('uncertain', 'what about the corn')?.intent).toBe('interrupt');
  });

  it('stays suppressed when all its words are still only an acknowledgement, a stop or noise', () => {
    expect(assessFinalOverlap('backchannel', 'Yeah.')?.intent).toBe('backchannel');
    expect(assessFinalOverlap('backchannel', 'Yeah, okay.')?.intent).toBe('backchannel');
    expect(assessFinalOverlap('hard_stop', 'Stop.')?.intent).toBe('hard_stop');
    expect(assessFinalOverlap('noise', '[noise]')?.intent).toBe('noise');
  });

  it('keeps an interruption already acted on, and has nothing to judge without an overlap', () => {
    expect(assessFinalOverlap('interrupt', 'okay')).toBeNull();
    expect(assessFinalOverlap(null, 'okay')).toBeNull();
  });
});
