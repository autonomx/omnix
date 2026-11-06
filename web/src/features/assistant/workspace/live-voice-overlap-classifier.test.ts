import { afterEach, describe, expect, it } from 'vitest';

import {
  clearPlaybackEchoSuppression,
  markPlaybackEchoSuppressed,
} from './live-voice-echo-suppression';
import {
  classifyOverlap,
  isLikelyEcho,
  shouldConfirmInterruption,
} from './live-voice-overlap-classifier';

afterEach(() => clearPlaybackEchoSuppression());

describe('live voice overlap classifier', () => {
  it('confirms hard stops, corrections, questions, and sustained speech', () => {
    expect(classifyOverlap('stop').intent).toBe('hard_stop');
    expect(classifyOverlap('No, I meant the eastern road').intent).toBe('interrupt');
    expect(classifyOverlap('Where did you say the entrance was?').intent).toBe('interrupt');
    expect(shouldConfirmInterruption(classifyOverlap('I need to change the destination now'), 'balanced')).toBe(true);
  });

  it('leaves short remarks to the model, whatever the words', () => {
    // No list of reactions: people say anything. Only the model tells these apart.
    for (const remark of ['mhm', 'yeah', 'Yeah, okay.', 'right right', 'Uh', 'Huh?', 'Cool.', 'Sweet', 'Really?', 'What?', 'Hang on.', 'Vale.']) {
      const assessment = classifyOverlap(remark);
      expect(assessment.intent, remark).toBe('uncertain');
      expect(shouldConfirmInterruption(assessment, 'easy'), remark).toBe(false);
    }
  });

  it('knows noise without the model', () => {
    expect(classifyOverlap('[cough]').intent).toBe('noise');
    expect(classifyOverlap('...').intent).toBe('noise');
  });

  it.each([
    'No, not much.',
    "I don't have to explain anything.",
    'Uh, what about the corn',
    'Cool, but where did you go',
    'What do you mean',
    'yeah how is the farm',
  ])('still lets "%s" interrupt', (speech) => {
    const assessment = classifyOverlap(speech);
    expect(assessment.intent).toBe('interrupt');
    expect(shouldConfirmInterruption(assessment, 'easy')).toBe(true);
  });

  it('recognizes likely assistant echo', () => {
    const assistant = 'The entrance is beneath the old watchtower near the river.';
    const echo = 'entrance beneath the old watchtower near the river';
    expect(isLikelyEcho(echo, assistant)).toBe(true);
    expect(classifyOverlap(echo, assistant).intent).toBe('noise');
  });

  it('suppresses semantic interruption while the acoustic gate identifies playback echo', () => {
    const sustained = classifyOverlap('I need to change the destination now');
    const hardStop = classifyOverlap('stop');
    markPlaybackEchoSuppressed('echo_residual_matches_playback');

    expect(shouldConfirmInterruption(sustained, 'easy')).toBe(false);
    expect(shouldConfirmInterruption(hardStop, 'finish_more')).toBe(false);

    clearPlaybackEchoSuppression();
    expect(shouldConfirmInterruption(hardStop, 'finish_more')).toBe(true);
  });

  it('allows users to tune ambiguous sustained overlap without weakening hard stops', () => {
    const sustained = classifyOverlap('I need to change the destination now');
    const hardStop = classifyOverlap('stop');
    expect(sustained.confidence).toBe(0.74);
    expect(shouldConfirmInterruption(sustained, 'easy')).toBe(true);
    expect(shouldConfirmInterruption(sustained, 'balanced')).toBe(true);
    expect(shouldConfirmInterruption(sustained, 'finish_more')).toBe(false);
    expect(shouldConfirmInterruption(hardStop, 'finish_more')).toBe(true);
  });
});
