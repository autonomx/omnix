import { describe, expect, it } from 'vitest';

import {
  assessSemanticTurn,
  conversationTimingProfile,
  reduceUserFloor,
  semanticFinalizeDelay,
} from './live-voice-floor-manager';

describe('live voice floor manager', () => {
  it('waits longer for hesitation and unfinished clauses', () => {
    const hesitation = assessSemanticTurn('I think we should um', 'balanced');
    const unfinished = assessSemanticTurn('We should take the road because', 'balanced');
    const command = assessSemanticTurn('Open the inventory', 'balanced');

    expect(hesitation.reason).toBe('trailing_hesitation');
    expect(unfinished.reason).toBe('unfinished_clause');
    expect(command.reason).toBe('complete_command');
    expect(hesitation.recommendedWaitMs).toBeGreaterThan(command.recommendedWaitMs);
    expect(unfinished.recommendedWaitMs).toBeGreaterThan(command.recommendedWaitMs);
  });

  it('uses a bounded 220 ms balanced fast path for clear questions and commands', () => {
    expect(semanticFinalizeDelay('Where are we going?', 'balanced')).toBe(220);
    expect(semanticFinalizeDelay('Open the inventory', 'balanced')).toBe(220);
  });

  it('does not apply the clear-turn fast path to ordinary statements', () => {
    expect(semanticFinalizeDelay('The road looks dangerous', 'balanced')).toBe(360);
    expect(semanticFinalizeDelay('We should take the road because', 'balanced')).toBe(1_000);
  });

  it('provides bounded quick balanced and reflective profiles', () => {
    expect(semanticFinalizeDelay('Open the inventory', 'quick')).toBeLessThan(
      semanticFinalizeDelay('Open the inventory', 'reflective'),
    );
    expect(semanticFinalizeDelay('I think we should um', 'reflective')).toBe(
      conversationTimingProfile('reflective').maximumWaitMs,
    );
  });

  it('uses the ambiguous pause instead of the maximum pause before partial STT is ready', () => {
    const profile = conversationTimingProfile('balanced');

    expect(semanticFinalizeDelay('', 'balanced')).toBe(profile.ambiguousWaitMs);
    expect(semanticFinalizeDelay('', 'balanced')).toBeLessThan(profile.maximumWaitMs);
  });

  it('keeps user-floor state independent from assistant lifecycle', () => {
    let state = reduceUserFloor('idle', { type: 'listen' });
    state = reduceUserFloor(state, { type: 'speech_candidate' });
    state = reduceUserFloor(state, { type: 'speech_confirmed', assistantSpeaking: false });
    expect(state).toBe('speaking');
    state = reduceUserFloor(state, { type: 'pause' });
    expect(state).toBe('paused');
    state = reduceUserFloor(state, { type: 'completion_check' });
    expect(state).toBe('completion_pending');
    state = reduceUserFloor(state, { type: 'commit' });
    expect(state).toBe('listening');
  });
});
