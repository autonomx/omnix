import { QueryClientProvider, useQuery } from '@tanstack/react-query';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ChatSidebarSessions } from './ChatSidebarSessions';
import { characterClient } from './characterClient';
import { initializeLiveChatWorkspace } from './live-chat-workspace';
import { NewChatButton } from './NewChatButton';
import { installSessionTools } from './sessionTools';
import { useChatSessions } from './useChatSessions';
import { createTestQueryClient } from '../../../test/renderWithProviders';

const settings = { interaction_mode: 'system', character_id: null, voice_asset_id: null, read_memory: false, write_memory: false, shared_memory_access: 'none', transcript_policy: 'persistent' };
const session = (id: string) => ({ id, title: id, message_count: 0, messages: [], created_at: '2026-06-14T00:00:00Z', updated_at: '2026-06-14T00:00:00Z', ...settings });

const OLDER = 'chat:older';

let disposers: Array<() => void> = [];

/** The sidebar, the selection and the fetch middleware together, with the older chat's interaction answer held back. */
function renderChat() {
  const server = [OLDER];
  const heldAnswers: Array<() => void> = [];
  let created = 0;
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const raw = typeof input === 'string' || input instanceof URL ? input.toString() : input.url;
    const method = (init?.method ?? (input instanceof Request ? input.method : 'GET')).toUpperCase();
    const path = decodeURIComponent(new URL(raw, window.location.origin).pathname);
    if (path === '/api/chat/sessions' && method === 'POST') {
      created += 1;
      const id = `chat:new-${created}`;
      server.unshift(id);
      return Response.json(session(id));
    }
    if (path === '/api/chat/sessions') return Response.json({ sessions: server.map(session) });
    if (path === `/api/chat/sessions/${OLDER}/interaction`) {
      await new Promise<void>((resolve) => heldAnswers.push(resolve));
      return Response.json(settings);
    }
    if (path.endsWith('/interaction')) return Response.json(settings);
    return Response.json(session(path.split('/').pop() ?? ''));
  }));

  const client = createTestQueryClient();
  const selection: { current: string | null } = { current: null };
  function Chat() {
    const chat = useChatSessions({ setActiveView: () => undefined, setAudioStatus: () => undefined });
    const selected = chat.selectedSessionId;
    selection.current = selected;
    // Chat's own per-session request: the one that can come back after the chat was left.
    useQuery({ queryKey: ['interaction', selected], queryFn: () => characterClient.session(selected ?? ''), enabled: Boolean(selected) });
    return (
      <>
        <NewChatButton />
        <ChatSidebarSessions sessions={chat.chatSessions} loading={chat.sessionsLoading} failed={chat.sessionsError} selectedSessionId={selected} onSelect={chat.selectSidebarSession} onDelete={async () => undefined} />
      </>
    );
  }
  disposers = [installSessionTools(), initializeLiveChatWorkspace(client)];
  render(<QueryClientProvider client={client}><Chat /></QueryClientProvider>);
  return { selection, heldAnswers };
}

const sidebarRows = () => [...document.querySelectorAll('[data-session-id]')].map((row) => row.getAttribute('data-session-id'));

afterEach(() => {
  cleanup();
  disposers.forEach((dispose) => dispose());
  disposers = [];
  vi.unstubAllGlobals();
  window.history.replaceState(null, '', '/');
});

describe('clicking New chat', () => {
  it('stays on the new chat when an answer for the previous chat comes back late, and lists it', async () => {
    const { selection, heldAnswers } = renderChat();
    await waitFor(() => expect(heldAnswers).toHaveLength(1));

    fireEvent.click(screen.getByRole('button', { name: 'New chat' }));
    await waitFor(() => expect(selection.current).toBe('chat:new-1'));
    await act(async () => {
      heldAnswers.splice(0).forEach((release) => release());
      await new Promise((resolve) => setTimeout(resolve, 20));
    });

    expect(selection.current).toBe('chat:new-1');
    await waitFor(() => expect(sidebarRows()).toEqual(['chat:new-1', OLDER]));
  });

  it('moves to, marks and lists a further new chat on each click', async () => {
    const { selection, heldAnswers } = renderChat();
    await waitFor(() => expect(heldAnswers).toHaveLength(1));

    fireEvent.click(screen.getByRole('button', { name: 'New chat' }));
    await waitFor(() => expect(selection.current).toBe('chat:new-1'));
    await waitFor(() => expect(screen.getByRole('button', { name: 'New chat' })).not.toBeDisabled());

    fireEvent.click(screen.getByRole('button', { name: 'New chat' }));
    await waitFor(() => expect(selection.current).toBe('chat:new-2'));

    await waitFor(() => expect(sidebarRows()).toEqual(['chat:new-2', 'chat:new-1', OLDER]));
    expect(document.querySelector('.assistant-chatgpt-row.active')).toHaveAttribute('data-session-id', 'chat:new-2');
  });
});
