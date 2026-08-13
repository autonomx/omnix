import { QueryClient } from '@tanstack/react-query';
import { waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  closeLiveChat,
  initializeLiveChatWorkspace,
  installLiveChatNavigation,
  openLiveChat,
  sessionIdFromChatRequest,
} from './live-chat-workspace';

const defaultProfile = {
  presence_preset: 'natural', talkativeness: 50, conversation_stance: 'automatic',
  conversation_pace: 'balanced', interruption_preference: 'balanced', assistant_backchannel_mode: 'off',
  initiative_mode: 'gentle', idle_threshold_ms: 15000, long_pause_behavior: 'wait',
  response_length: 'conversational', response_onset_style: 'adaptive', emotional_attunement: 'subtle',
  topic_continuity: 'natural', max_idle_prompts: 1, duplex_mode: 'automatic',
  pronunciation_save_policy: 'ask', profile_version: 1,
};

let disposeWorkspace: (() => void) | null = null;

afterEach(() => {
  disposeWorkspace?.();
  disposeWorkspace = null;
  closeLiveChat();
  document.body.innerHTML = '';
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function installWorkspaceShell(): void {
  document.body.innerHTML = `
    <nav class="assistant-sidebar-nav">
      <button type="button"><span>Chats</span></button>
      <button type="button" class="active" aria-current="page"><span>Voice Sessions</span></button>
    </nav>
    <main class="assistant-chat-main"><div data-existing-view>Chats view</div></main>
  `;
}

describe('live chat workspace controller', () => {
  it('recognizes the selected chat session from session API requests', () => {
    expect(sessionIdFromChatRequest('/api/chat/sessions/chat%3Aone')).toBe('chat:one');
    expect(sessionIdFromChatRequest('/api/chat/sessions/chat%3Aone/live-call/runtime')).toBe('chat:one');
    expect(sessionIdFromChatRequest('/api/chat/sessions')).toBeNull();
  });

  it('adds Live Chat immediately after Chats and mounts one workspace host', () => {
    installWorkspaceShell();
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    disposeWorkspace = initializeLiveChatWorkspace(queryClient);

    const button = installLiveChatNavigation();
    expect(button?.textContent).toContain('Live Chat');
    expect(button?.previousElementSibling?.textContent).toContain('Chats');

    openLiveChat();
    expect(document.querySelector('.assistant-chat-main')).toHaveClass('omnix-live-chat-active');
    expect(document.querySelectorAll('[data-omnix-live-chat-host]')).toHaveLength(1);
    expect(button).toHaveClass('active');
    expect(button).toHaveAttribute('aria-current', 'page');
    expect(button?.parentElement?.querySelectorAll('button.active')).toHaveLength(1);
    expect(button?.nextElementSibling).not.toHaveClass('active');

    openLiveChat();
    expect(document.querySelectorAll('[data-omnix-live-chat-host]')).toHaveLength(1);
  });

  it('reconciles persisted chat history after terminal live response diagnostics', async () => {
    installWorkspaceShell();
    vi.stubGlobal('fetch', vi.fn(async () => Response.json({ ok: true })));
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const invalidateQueries = vi.spyOn(queryClient, 'invalidateQueries').mockResolvedValue();
    disposeWorkspace = initializeLiveChatWorkspace(queryClient);

    await window.fetch('/api/chat/sessions/chat%3Aone/interaction');
    window.dispatchEvent(new CustomEvent('omnix:live-call-diagnostic', {
      detail: { event: 'turn_finished', details: { turn_kind: 'response' } },
    }));

    await waitFor(() => {
      expect(invalidateQueries).toHaveBeenCalledWith({
        queryKey: ['feature', 'chatbot', 'session', 'chat:one'],
        exact: true,
      });
      expect(invalidateQueries).toHaveBeenCalledWith({
        queryKey: ['feature', 'chatbot', 'sessions'],
        exact: true,
      });
    });

    invalidateQueries.mockClear();
    window.dispatchEvent(new CustomEvent('omnix:live-call-diagnostic', {
      detail: { event: 'turn_finished', details: { turn_kind: 'greeting' } },
    }));
    expect(invalidateQueries).not.toHaveBeenCalled();
  });

  it('mounts a selected-session Live Chat panel with the application QueryClient', async () => {
    installWorkspaceShell();
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = input.toString();
      if (url === '/api/characters') return Response.json({ characters: [] });
      if (url.includes('/interaction')) {
        return Response.json({
          id: 'chat:one', title: 'Test chat', interaction_mode: 'system', character_id: null,
          voice_asset_id: null, read_memory: false, write_memory: false,
          shared_memory_access: 'none', transcript_policy: 'persistent', messages: [],
        });
      }
      if (url.includes('/live-conversation/pronunciations')) {
        return Response.json({ session_id: 'chat:one', entries: [] });
      }
      if (url.includes('/live-conversation/profile')) {
        return Response.json({
          session_id: 'chat:one', source: 'user_defaults', defaults: defaultProfile,
          session_override: null, effective: defaultProfile,
        });
      }
      return Response.json(defaultProfile);
    }));

    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    disposeWorkspace = initializeLiveChatWorkspace(queryClient);
    await window.fetch('/api/chat/sessions/chat%3Aone/interaction');
    document.querySelector<HTMLButtonElement>('[data-omnix-live-chat-nav]')?.click();

    await waitFor(() => {
      expect(document.querySelector('[aria-label="Character Mode settings"]')).toBeInTheDocument();
      expect(document.querySelector('[data-omnix-live-chat-host]')).toHaveTextContent('Live Chat');
    });
  });
});
