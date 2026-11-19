import { afterEach, describe, expect, it } from 'vitest';

import {
  closeProposalQuestion,
  markProposalQuestionAudible,
  noteUserSpeechOnset,
  openProposalQuestion,
  PROPOSAL_ANSWER_WINDOW_MS,
  proposalButtonsVisible,
  proposalQuestionAwaitsVoice,
  proposalQuestionStore,
  takeHeardProposalTurnId,
} from './live-call-proposal-question';

const TASK = 'call-task:m1:0';
const TURN = `task-report:${TASK}`;
const AUDIBLE_AT = 1_000_000;

function ask(): void {
  openProposalQuestion('s1', TASK, TURN);
  markProposalQuestionAudible(TURN, AUDIBLE_AT);
}

afterEach(() => proposalQuestionStore.resetForTests());

describe('the proposal question', () => {
  it('lets the first voice turn carry the question only when speech began after its audio', () => {
    openProposalQuestion('s1', TASK, TURN);
    noteUserSpeechOnset(AUDIBLE_AT - 500);  // still speaking about something else when the question was made
    markProposalQuestionAudible(TURN, AUDIBLE_AT);
    expect(takeHeardProposalTurnId('s1', AUDIBLE_AT + 2_000)).toBeNull();

    ask();
    noteUserSpeechOnset(AUDIBLE_AT + 800);
    expect(takeHeardProposalTurnId('other', AUDIBLE_AT + 2_000)).toBeNull();
    expect(takeHeardProposalTurnId('s1', AUDIBLE_AT + 2_000)).toBe(TURN);
    expect(takeHeardProposalTurnId('s1', AUDIBLE_AT + 9_000)).toBeNull();  // only the first turn may answer aloud
  });

  it('does not count speech before the question was heard, or after its window', () => {
    openProposalQuestion('s1', TASK, TURN);
    noteUserSpeechOnset(AUDIBLE_AT + 100);  // its audio has not begun
    expect(takeHeardProposalTurnId('s1', AUDIBLE_AT + 200)).toBeNull();

    ask();
    noteUserSpeechOnset(AUDIBLE_AT + PROPOSAL_ANSWER_WINDOW_MS + 1);
    expect(takeHeardProposalTurnId('s1', AUDIBLE_AT + PROPOSAL_ANSWER_WINDOW_MS + 2)).toBeNull();
  });

  it('awaits a spoken answer and shows its buttons only while it can be answered', () => {
    openProposalQuestion('s1', TASK, TURN);
    expect(proposalQuestionAwaitsVoice('s1', AUDIBLE_AT)).toBe(false);
    expect(proposalButtonsVisible(proposalQuestionStore.getState(), 's1', AUDIBLE_AT)).toBe(false);

    markProposalQuestionAudible(TURN, AUDIBLE_AT);
    expect(proposalQuestionAwaitsVoice('s1', AUDIBLE_AT + 1)).toBe(true);
    expect(proposalQuestionAwaitsVoice('s2', AUDIBLE_AT + 1)).toBe(false);
    expect(proposalButtonsVisible(proposalQuestionStore.getState(), 's1', AUDIBLE_AT + 1)).toBe(true);
    expect(proposalButtonsVisible(proposalQuestionStore.getState(), 's2', AUDIBLE_AT + 1)).toBe(false);
    expect(proposalButtonsVisible(proposalQuestionStore.getState(), 's1', AUDIBLE_AT + PROPOSAL_ANSWER_WINDOW_MS + 1))
      .toBe(false);

    takeHeardProposalTurnId('s1', AUDIBLE_AT + 5);
    expect(proposalQuestionAwaitsVoice('s1', AUDIBLE_AT + 6)).toBe(false);
    // The buttons stay: the server lets them answer within the window whatever was said.
    expect(proposalButtonsVisible(proposalQuestionStore.getState(), 's1', AUDIBLE_AT + 6)).toBe(true);

    closeProposalQuestion();
    expect(proposalQuestionStore.getState().question).toBeNull();
  });

  it('ignores the audio of another turn', () => {
    openProposalQuestion('s1', TASK, TURN);
    markProposalQuestionAudible('task-report:call-task:m2:0', AUDIBLE_AT);
    expect(proposalQuestionStore.getState().question?.audibleAtMs).toBeNull();
  });
});
