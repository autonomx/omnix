import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  initializeChatSidebarManager,
  readChatSidebarState,
  sortChatSidebarSessions,
  visibleChatSidebarSessions,
  writeChatSidebarState,
} from './chat-sidebar-manager';

describe('chat sidebar manager', () => {
  let dispose: () => void;
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    window.localStorage.clear();
    document.body.innerHTML = `
      <aside class="assistant-chat-sidebar">
        <nav class="assistant-sidebar-nav">
          <button type="button" aria-label="Open Chats view">Chats</button>
        </nav>
        <section class="assistant-sidebar-section assistant-sidebar-sessions" aria-labelledby="assistant-chat-sessions">
          <header><h2 id="assistant-chat-sessions">Sessions</h2></header>
        </section>
        <section class="assistant-sidebar-section" aria-labelledby="assistant-chat-pinned">
          <header><h2 id="assistant-chat-pinned">Pinned</h2></header>
        </section>
        <section class="assistant-sidebar-section" aria-labelledby="assistant-chat-recent">
          <header><h2 id="assistant-chat-recent">Recent</h2></header>
        </section>
      </aside>
      <section class="assistant-chat-header"><h2>Current chat</h2></section>
      <label class="assistant-message-input">
        <textarea name="content" placeholder="Message Omnix Assistant, or use the microphone…">old draft</textarea>
      </label>
    `;
    fetchMock = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      if (String(init?.method ?? 'GET').toUpperCase() === 'POST') {
        return Response.json({
          id: 'chat:new-session',
          title: 'New chat',
          messages: [],
          message_count: 0,
        });
      }
      return Response.json({
        sessions: [
          { id: 'chat:one', title: 'First chat', provider_id: 'lm-studio', model_id: 'local-model', interaction_mode: 'character', character_id: 'maya', voice_asset_id: 'voice-cloning:Maya', read_memory: true, write_memory: false, shared_memory_access: 'read_only', transcript_policy: 'temporary', message_count: 12, created_at: '2026-08-08T00:00:00Z', updated_at: '2026-08-08T00:01:00Z' },
          { id: 'chat:two', title: 'Second chat', message_count: 4, created_at: '2026-08-08T00:00:00Z', updated_at: '2026-08-08T00:02:00Z' },
        ],
      });
    });
    vi.stubGlobal('fetch', fetchMock);
    dispose = initializeChatSidebarManager();
  });

  afterEach(() => {
    dispose?.();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    window.localStorage.clear();
    document.body.innerHTML = '';
  });

  it('places the newest chat session first', () => {
    const sessions = [
      { id: 'chat:old', title: 'Older chat', updated_at: '2026-08-08T00:01:00Z' },
      { id: 'chat:new', title: 'New chat', created_at: '2026-08-08T00:03:00Z' },
      { id: 'chat:middle', title: 'Middle chat', updated_at: '2026-08-08T00:02:00Z' },
    ];

    expect(sortChatSidebarSessions(sessions).map((session) => session.id)).toEqual([
      'chat:new',
      'chat:middle',
      'chat:old',
    ]);
  });

  it('renders Pinned before Sessions with one New control and ChatGPT-style row actions', async () => {
    await vi.waitFor(() => {
      expect(document.querySelector('[data-omnix-chat-sidebar-manager="true"]')).not.toBeNull();
      expect(document.querySelectorAll('.assistant-chatgpt-row')).toHaveLength(2);
    });

    const headings = [...document.querySelectorAll<HTMLElement>('.assistant-chatgpt-section h2')]
      .map((heading) => heading.textContent);
    expect(headings).toEqual(['Pinned', 'Sessions']);
    expect(document.querySelectorAll<HTMLButtonElement>('.assistant-chatgpt-new')).toHaveLength(1);
    expect(document.querySelector('[aria-labelledby="assistant-chat-sessions"]')).toHaveAttribute('hidden');
    expect(document.querySelector('[aria-labelledby="assistant-chat-pinned"]')).toHaveAttribute('hidden');
    expect(document.querySelector('[aria-labelledby="assistant-chat-recent"]')).toHaveAttribute('hidden');

    const firstRow = document.querySelector<HTMLElement>('.assistant-chatgpt-row[data-session-id="chat:one"]');
    expect(firstRow?.querySelector('.assistant-chatgpt-pin')).toHaveAccessibleName('Pin First chat');
    expect(firstRow?.querySelector('.assistant-chatgpt-more')).toHaveAccessibleName('More options for First chat');

    firstRow?.querySelector<HTMLButtonElement>('.assistant-chatgpt-more')?.click();
    await vi.waitFor(() => {
      const menuItems = [...document.querySelectorAll<HTMLElement>('.assistant-chatgpt-menu [role="menuitem"]')]
        .map((item) => item.textContent?.replace(/^[^A-Za-z]+/, '').trim());
      expect(menuItems).toEqual(['Share', 'Rename', 'Pin chat', 'Archive', 'Delete']);
    });
  });

  it('starts the managed New chat in place and selects it without navigation', async () => {
    await vi.waitFor(() => expect(document.querySelector<HTMLButtonElement>('.assistant-chatgpt-new')).not.toBeNull());

    const selectedSessions: string[] = [];
    const createdSessions: unknown[] = [];
    const stopEvents = vi.fn();
    window.addEventListener('omnix:live-chat-session-changed', (event) => {
      selectedSessions.push((event as CustomEvent<{ sessionId: string }>).detail.sessionId);
    }, { once: true });
    window.addEventListener('omnix:chat-session-created', (event) => {
      createdSessions.push((event as CustomEvent<{ session: unknown }>).detail.session);
    }, { once: true });
    window.addEventListener('omnix:assistant-live-voice-stop', stopEvents, { once: true });

    document.querySelector<HTMLButtonElement>('.assistant-chatgpt-new')?.click();

    await vi.waitFor(() => expect(selectedSessions).toEqual(['chat:new-session']));
    const postCall = fetchMock.mock.calls.find(([, init]) => String(init?.method ?? 'GET').toUpperCase() === 'POST');
    expect(postCall).toBeDefined();
    expect(createdSessions).toHaveLength(1);
    expect(stopEvents).toHaveBeenCalledTimes(1);
    expect(document.querySelector<HTMLTextAreaElement>('textarea[name="content"]')?.value).toBe('');
  });

  it('uses the selected session summary instead of rereading the transcript', async () => {
    await vi.waitFor(() => expect(document.querySelectorAll('.assistant-chatgpt-row')).toHaveLength(2));
    document.querySelector<HTMLButtonElement>(
      '.assistant-chatgpt-row[data-session-id="chat:one"] .assistant-chatgpt-session',
    )?.click();
    fetchMock.mockClear();

    document.querySelector<HTMLButtonElement>('.assistant-chatgpt-new')?.click();

    await vi.waitFor(() => {
      const postCall = fetchMock.mock.calls.find(([, init]) => String(init?.method ?? 'GET').toUpperCase() === 'POST');
      expect(postCall).toBeDefined();
      expect(JSON.parse(String(postCall?.[1]?.body))).toMatchObject({
        title: 'New chat',
        provider_id: 'lm-studio',
        model_id: 'local-model',
        interaction_mode: 'character',
        character_id: 'maya',
        voice_asset_id: 'voice-cloning:Maya',
        read_memory: true,
        write_memory: false,
        shared_memory_access: 'read_only',
        transcript_policy: 'temporary',
      });
    });
    expect(fetchMock.mock.calls.some(([input]) => String(input).includes('/chat:one'))).toBe(false);
  });

  it('moves a pinned chat out of Sessions and into Pinned', async () => {
    await vi.waitFor(() => expect(document.querySelectorAll('.assistant-chatgpt-row')).toHaveLength(2));

    document.querySelector<HTMLButtonElement>(
      '.assistant-chatgpt-row[data-session-id="chat:one"] .assistant-chatgpt-pin',
    )?.click();

    await vi.waitFor(() => {
      const pinned = document.querySelector<HTMLElement>(
        '.assistant-chatgpt-section[aria-labelledby="assistant-chatgpt-pinned"] .assistant-chatgpt-row[data-session-id="chat:one"]',
      );
      const regular = document.querySelector<HTMLElement>(
        '.assistant-chatgpt-section[aria-labelledby="assistant-chatgpt-sessions"] .assistant-chatgpt-row[data-session-id="chat:one"]',
      );
      expect(pinned).not.toBeNull();
      expect(regular).toBeNull();
    });
    expect(readChatSidebarState()['chat:one']?.pinned).toBe(true);
  });

  it('does not refetch sessions for unrelated live-render mutations', async () => {
    await vi.waitFor(() => expect(document.querySelectorAll('.assistant-chatgpt-row')).toHaveLength(2));
    const fetchCount = fetchMock.mock.calls.length;

    const transcript = document.createElement('p');
    transcript.textContent = 'Streaming transcript update';
    document.querySelector('.assistant-chat-header')?.appendChild(transcript);
    transcript.textContent = 'Streaming transcript update with more text';
    await new Promise((resolve) => window.setTimeout(resolve, 120));

    expect(fetchMock).toHaveBeenCalledTimes(fetchCount);
  });

  it('persists local sidebar state and filters archived and podcast sessions', () => {
    writeChatSidebarState({
      'chat:archived': { archived: true },
      'chat:pinned': { pinned: true, title: 'Renamed locally' },
    });
    expect(readChatSidebarState()['chat:pinned']).toEqual({ pinned: true, title: 'Renamed locally' });

    const visible = visibleChatSidebarSessions([
      { id: 'chat:archived', title: 'Old chat' },
      { id: 'chat:pinned', title: 'Pinned chat' },
      { id: 'chat:podcast', title: 'Podcast script: episode 1' },
      { id: 'chat:normal', title: 'Normal chat' },
    ], readChatSidebarState());
    expect(visible.map((session) => session.id)).toEqual(['chat:pinned', 'chat:normal']);
  });
});
