import { useSyncExternalStore } from 'react';

import { ApiError } from '../../../api/errors';
import { unwrap } from '../../../api/http';
import { api } from '../api/gateway';

/**
 * The question a call asks about a proposed action (live companion roadmap WP 1.5): "Turn off the desk lamp?". The
 * server decides whether a turn answers it; this module only tells it what the call saw: that the person began
 * speaking after the question's audio did (`heard_turn_id`), and which question the Confirm/Cancel buttons are for.
 */

/** The server's `PROPOSAL_CONFIRM_WINDOW`: after two minutes the question has expired. */
export const PROPOSAL_ANSWER_WINDOW_MS = 120_000;
/** How long a button's result stays on screen. */
export const PROPOSAL_OUTCOME_SHOWN_MS = 8_000;

export type ProposalQuestion = {
  sessionId: string;
  taskId: string;
  /** The report turn that asks it, `task-report:<task_id>`: what a voice answer sends as `heard_turn_id`. */
  turnId: string;
  /** Wall time its audio began; null until the person can hear it. */
  audibleAtMs: number | null;
  /** The person began speaking after the audio did. */
  heard: boolean;
  /** A voice turn has gone to the server since: only the first may answer by voice. */
  answeredByVoice: boolean;
};

export type ProposalDecisionOutcome = {
  taskId: string;
  status: 'executed' | 'failed' | 'rejected' | 'unavailable';
  text: string;
};

export type ProposalQuestionState = {
  question: ProposalQuestion | null;
  deciding: boolean;
  outcome: ProposalDecisionOutcome | null;
};

const UNAVAILABLE_TEXT: Record<string, string> = {
  proposal_decided: 'That was already answered.',
  proposal_expired: 'That question has expired. Ask again to do it.',
  proposal_not_found: 'That question is no longer in this chat.',
};

let state: ProposalQuestionState = { question: null, deciding: false, outcome: null };
const listeners = new Set<() => void>();
let expiryTimer: ReturnType<typeof setTimeout> | null = null;

function setState(change: Partial<ProposalQuestionState>): void {
  state = { ...state, ...change };
  listeners.forEach((listener) => listener());
}

export const proposalQuestionStore = {
  getState(): ProposalQuestionState {
    return state;
  },

  subscribe(listener: () => void): () => void {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },

  resetForTests(): void {
    clearExpiryTimer();
    state = { question: null, deciding: false, outcome: null };
    listeners.forEach((listener) => listener());
  },
};

export function useProposalQuestion(): ProposalQuestionState {
  return useSyncExternalStore(proposalQuestionStore.subscribe, proposalQuestionStore.getState, proposalQuestionStore.getState);
}

/** A report that asks about a proposal has been generated; it is not yet heard. */
export function openProposalQuestion(sessionId: string, taskId: string, turnId: string): void {
  clearExpiryTimer();
  setState({
    question: { sessionId, taskId, turnId, audibleAtMs: null, heard: false, answeredByVoice: false },
    deciding: false,
    outcome: null,
  });
}

/** The report's audio has begun: from now the person can answer it. */
export function markProposalQuestionAudible(turnId: string, nowMs: number = Date.now()): void {
  const question = state.question;
  if (!question || question.turnId !== turnId || question.audibleAtMs !== null) return;
  setState({ question: { ...question, audibleAtMs: nowMs } });
  clearExpiryTimer();
  expiryTimer = setTimeout(() => {
    expiryTimer = null;
    if (state.question === null || state.question.turnId !== turnId) return;
    setState({ question: { ...state.question } });  // the buttons read the window again and go
  }, PROPOSAL_ANSWER_WINDOW_MS + 50);
}

/** The person began to speak (voice activity onset). Speech that began earlier, even if it ends later, is not heard. */
export function noteUserSpeechOnset(nowMs: number = Date.now()): void {
  const question = state.question;
  if (!question || question.heard || question.answeredByVoice || !withinWindow(question, nowMs)) return;
  setState({ question: { ...question, heard: true } });
}

/**
 * A voice turn is going to the server: the first since the question was heard carries its turn id, so the server
 * may read it as the answer. Any voice turn ends the spoken path, as on the server, which accepts only the first.
 */
export function takeHeardProposalTurnId(sessionId: string, nowMs: number = Date.now()): string | null {
  const question = state.question;
  if (!question || question.sessionId !== sessionId || question.audibleAtMs === null || question.answeredByVoice) {
    return null;
  }
  setState({ question: { ...question, answeredByVoice: true } });
  return question.heard && withinWindow(question, nowMs) ? question.turnId : null;
}

/** While the question can still be answered aloud, a confirm or cancel said over it must reach the server. */
export function proposalQuestionAwaitsVoice(sessionId: string, nowMs: number = Date.now()): boolean {
  const question = state.question;
  return Boolean(question && question.sessionId === sessionId && !question.answeredByVoice && withinWindow(question, nowMs));
}

/** The buttons show for a heard question within its window, until one is pressed. */
export function proposalButtonsVisible(current: ProposalQuestionState = state, sessionId: string | null = null,
  nowMs: number = Date.now()): boolean {
  const question = current.question;
  if (!question || current.outcome || (sessionId !== null && question.sessionId !== sessionId)) return false;
  return withinWindow(question, nowMs);
}

/** The call's Confirm/Cancel buttons; the server checks the proposal and decides at most once. */
export async function decideProposalQuestion(decision: 'confirm' | 'cancel'): Promise<void> {
  const question = state.question;
  if (!question || state.deciding) return;
  setState({ deciding: true });
  let outcome: ProposalDecisionOutcome;
  try {
    const decided = await unwrap(api.POST('/api/chat/sessions/{session_id}/live-call/tasks/{task_id}/decision', {
      params: { path: { session_id: question.sessionId, task_id: question.taskId } },
      body: { decision },
    }));
    outcome = { taskId: decided.task_id, status: decided.status, text: decided.text };
  } catch (error) {
    const detail = error instanceof ApiError ? error.detail : '';
    outcome = { taskId: question.taskId, status: 'unavailable', text: UNAVAILABLE_TEXT[detail] ?? 'That did not go through.' };
  }
  if (state.question?.taskId !== question.taskId) {
    setState({ deciding: false });
    return;
  }
  setState({ deciding: false, outcome });
  clearExpiryTimer();
  expiryTimer = setTimeout(() => {
    expiryTimer = null;
    if (state.outcome === outcome) setState({ question: null, outcome: null });
  }, PROPOSAL_OUTCOME_SHOWN_MS);
}

/** The call ended or moved to another chat. */
export function closeProposalQuestion(): void {
  clearExpiryTimer();
  if (state.question || state.outcome || state.deciding) setState({ question: null, deciding: false, outcome: null });
}

function withinWindow(question: ProposalQuestion, nowMs: number): boolean {
  return question.audibleAtMs !== null && nowMs >= question.audibleAtMs
    && nowMs - question.audibleAtMs <= PROPOSAL_ANSWER_WINDOW_MS;
}

function clearExpiryTimer(): void {
  if (expiryTimer !== null) clearTimeout(expiryTimer);
  expiryTimer = null;
}
