import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  initializeChatSidebarManager,
  readChatSidebarState,
  visibleChatSidebarSessions,
  writeChatSidebarState,
} from './chat-sidebar-manager';

describe('chat sidebar manager', () => {
  let dispose: () => void;

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
    `;
    const fetchMock = vi.fn(async () => Response.json({
      sessions: [
        { id: 'chat:one', title: 'First chat', message_count: 12, created_at: '2026-08-08T00:00:00Z', updated_at: '2026-08-08T00:01:00Z' },
        { id: 'chat:two', title: 'Second chat', message_count: 4, created_at: '2026-08-08T00:00:00Z', updated_at: '2026-08-08T00:02:00Z' },
      ],
    }));
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
