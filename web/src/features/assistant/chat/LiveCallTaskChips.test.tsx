import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ASSISTANT_LIVE_VOICE_CALL_CONNECTED_EVENT, emitOmnixEvent } from '../../../events/bus';
import { markProposalQuestionAudible, openProposalQuestion, proposalQuestionStore } from '../workspace/live-call-proposal-question';
import { initializeLiveCallTasksController, liveCallTasksStore } from '../workspace/live-call-tasks-controller';
import { liveConversationStore } from '../workspace/live-conversation-store';
import { LiveCallTaskChips } from './LiveCallTaskChips';

type Task = {
  task_id: string;
  ability: string;
  query: string;
  state: 'open' | 'completed' | 'failed' | 'cancelled' | 'not_started';
  asked_at: string;
  settled_at: string | null;
  result_message_id: string | null;
  reported: boolean;
};

let tasks: Task[] = [];
let cancelPaths: string[] = [];
let decisions: Array<{ path: string; body: unknown }> = [];
let decisionResponse: Response | null = null;
let dispose: (() => void) | null = null;

function json(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } });
}

beforeEach(() => {
  cancelPaths = [];
  decisions = [];
  decisionResponse = null;
  tasks = [
    {
      task_id: 'call-task:m1:0',
      ability: 'deep_research',
      query: 'flights to Lisbon in March',
      state: 'open',
      asked_at: '2026-11-15T10:00:00Z',
      settled_at: null,
      result_message_id: null,
      reported: false,
    },
    {
      task_id: 'call-task:m1:1',
      ability: 'web_search',
      query: 'weather',
      state: 'completed',
      asked_at: '2026-11-15T10:00:00Z',
      settled_at: '2026-11-15T10:00:05Z',
      result_message_id: 'r1',
      reported: true,
    },
  ];
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const raw = typeof input === 'string' || input instanceof URL ? input.toString() : input.url;
    const path = new URL(raw, window.location.origin).pathname;
    if (path.endsWith('/decision')) {
      const body = input instanceof Request ? await input.clone().text() : String(init?.body ?? '');
      decisions.push({ path, body: JSON.parse(body) });
      return decisionResponse ?? json({ task_id: 'call-task:m1:0', status: 'executed', text: 'Desk lamp is off.' });
    }
    if (path.endsWith('/cancel')) {
      cancelPaths.push(path);
      tasks = tasks.map((task) => (task.task_id === 'call-task:m1:0' ? { ...task, state: 'cancelled' } : task));
      return json(tasks[0]);
    }
    if (path === '/api/chat/sessions/s1/live-call/tasks') return json({ tasks });
    return json(null);
  }));
  liveConversationStore.reset();
  liveCallTasksStore.resetForTests();
  dispose = initializeLiveCallTasksController();
  liveConversationStore.dispatch({ type: 'session', sessionId: 's1' });
  liveConversationStore.dispatch({ type: 'conversation', event: { type: 'connection', value: 'connected' } });
  emitOmnixEvent(ASSISTANT_LIVE_VOICE_CALL_CONNECTED_EVENT, { token: 1, timestamp: '2026-11-15T10:00:00Z' });
});

afterEach(() => {
  dispose?.();
  dispose = null;
  vi.unstubAllGlobals();
  liveConversationStore.reset();
  liveCallTasksStore.resetForTests();
  proposalQuestionStore.resetForTests();
});

describe('LiveCallTaskChips', () => {
  it('shows one chip per open task and cancels it', async () => {
    render(<LiveCallTaskChips />);

    const chip = await screen.findByText('Researching: flights to Lisbon in March');
    expect(chip.getAttribute('title')).toBe('flights to Lisbon in March');
    expect(screen.queryByText(/weather/)).toBeNull();

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Cancel: Researching: flights to Lisbon in March' }));
    });

    expect(cancelPaths).toEqual(['/api/chat/sessions/s1/live-call/tasks/call-task%3Am1%3A0/cancel']);
    await vi.waitFor(() => expect(screen.queryByRole('list', { name: 'Working on it' })).toBeNull());
  });

  it('renders nothing when no task is open', () => {
    liveCallTasksStore.resetForTests();
    const { container } = render(<LiveCallTaskChips />);
    expect(container.innerHTML).toBe('');
  });

  it('answers the question about a proposed action with Confirm, and shows what happened', async () => {
    render(<LiveCallTaskChips />);
    await screen.findByText('Researching: flights to Lisbon in March');
    expect(screen.queryByRole('button', { name: 'Confirm' })).toBeNull();

    act(() => {
      openProposalQuestion('s1', 'call-task:m1:0', 'task-report:call-task:m1:0');
      markProposalQuestionAudible('task-report:call-task:m1:0');
    });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));
    });

    expect(decisions).toEqual([{
      path: '/api/chat/sessions/s1/live-call/tasks/call-task%3Am1%3A0/decision',
      body: { decision: 'confirm' },
    }]);
    expect(await screen.findByRole('status')).toHaveTextContent('Desk lamp is off.');
    expect(screen.queryByRole('button', { name: 'Confirm' })).toBeNull();
  });

  it('says so when the question was already answered', async () => {
    decisionResponse = new Response(JSON.stringify({ detail: 'proposal_decided' }), {
      status: 409, headers: { 'Content-Type': 'application/json' },
    });
    render(<LiveCallTaskChips />);
    await screen.findByText('Researching: flights to Lisbon in March');
    act(() => {
      openProposalQuestion('s1', 'call-task:m1:0', 'task-report:call-task:m1:0');
      markProposalQuestionAudible('task-report:call-task:m1:0');
    });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    });

    expect(decisions.map((item) => item.body)).toEqual([{ decision: 'cancel' }]);
    expect(await screen.findByRole('status')).toHaveTextContent('That was already answered.');
  });
});
