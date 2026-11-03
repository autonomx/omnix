import { QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { useChatSessions } from './useChatSessions';
import { createTestQueryClient } from '../../../test/renderWithProviders';

const summary = (id: string) => ({
  id,
  title: id,
  message_count: 0,
  created_at: '2026-06-14T00:00:00Z',
  updated_at: '2026-06-14T00:00:00Z',
});

function renderSessions(listSessions: () => Promise<Response>) {
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
    const raw = typeof input === 'string' || input instanceof URL ? input.toString() : input.url;
    const path = new URL(raw, window.location.origin).pathname;
    if (path === '/api/chat/sessions') return listSessions();
    return Response.json({ ...summary(decodeURIComponent(path.split('/').pop() ?? '')), messages: [] });
  }));
  const client = createTestQueryClient();
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  return renderHook(() => useChatSessions({ setActiveView: vi.fn(), setAudioStatus: vi.fn() }), { wrapper });
}

const createChat = (id: string) => act(() => {
  window.dispatchEvent(new CustomEvent('omnix:chat-session-created', { detail: { session: summary(id) } }));
  window.dispatchEvent(new CustomEvent('omnix:live-chat-session-changed', { detail: { sessionId: id } }));
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('chat session selection', () => {
  it('lists a new chat without waiting for the window to regain focus', async () => {
    const lists: string[][] = [['chat:older']];
    const listSessions = vi.fn(async () => Response.json({ sessions: (lists.at(-1) ?? []).map(summary) }));
    const { result } = renderSessions(listSessions);
    await waitFor(() => expect(result.current.selectedSessionId).toBe('chat:older'));

    lists.push(['chat:new', 'chat:older']);
    createChat('chat:new');

    await waitFor(() => expect(result.current.chatSessions.map((session) => session.id)).toEqual(['chat:new', 'chat:older']));
    expect(result.current.selectedSessionId).toBe('chat:new');
  });

  it('does not fall back to an older chat on a list from before the selected chat existed', async () => {
    const lists: string[][] = [['chat:older']];
    const held: Array<() => void> = [];
    const listSessions = vi.fn(() => {
      const sessions = (lists.at(-1) ?? []).map(summary);
      if (listSessions.mock.calls.length === 1) return Promise.resolve(Response.json({ sessions }));
      return new Promise<Response>((resolve) => held.push(() => resolve(Response.json({ sessions }))));
    });
    const { result } = renderSessions(listSessions);
    await waitFor(() => expect(result.current.selectedSessionId).toBe('chat:older'));

    lists.push(['chat:second', 'chat:first', 'chat:older']);
    createChat('chat:first');
    createChat('chat:second');
    // A late answer from the first new chat: it was on no list the browser holds yet.
    act(() => {
      window.dispatchEvent(new CustomEvent('omnix:live-chat-session-changed', { detail: { sessionId: 'chat:first' } }));
    });

    expect(result.current.selectedSessionId).toBe('chat:first');
    await waitFor(() => expect(held.length).toBeGreaterThan(0));
    await act(async () => { held.splice(0).forEach((release) => release()); });
    await waitFor(() => expect(result.current.chatSessions).toHaveLength(3));
    expect(result.current.selectedSessionId).toBe('chat:first');
  });

  it('still leaves a chat that a current list no longer has', async () => {
    let sessions = ['chat:gone', 'chat:other'];
    const listSessions = vi.fn(async () => Response.json({ sessions: sessions.map(summary) }));
    const { result } = renderSessions(listSessions);
    await waitFor(() => expect(result.current.selectedSessionId).toBe('chat:gone'));

    sessions = ['chat:other'];
    await act(async () => { await result.current.sessionsQuery.refetch(); });

    await waitFor(() => expect(result.current.selectedSessionId).toBe('chat:other'));
  });
});
