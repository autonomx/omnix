import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  initializeNewChatCoordinator,
  resetNewChatCoordinatorForTests,
} from './newChatCoordinator';

describe('new chat coordinator', () => {
  let dispose: () => void;

  beforeEach(() => {
    resetNewChatCoordinatorForTests();
    document.body.innerHTML = `
      <section class="assistant-sidebar-sessions">
        <header><h2>Sessions</h2></header>
      </section>
      <label class="assistant-message-input">
        <textarea name="content" placeholder="Message Omnix Assistant, or use the microphone…">old draft</textarea>
      </label>
    `;
    dispose = initializeNewChatCoordinator();
  });

  afterEach(() => {
    dispose();
    resetNewChatCoordinatorForTests();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    document.body.innerHTML = '';
  });

  it('restores the missing New Chat control and selects the created empty session', async () => {
    const fetchMock = vi.fn(async () => Response.json({
      id: 'chat:new-session',
      title: 'New chat',
      messages: [],
      message_count: 0,
    }));
    vi.stubGlobal('fetch', fetchMock);

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

    const button = document.querySelector<HTMLButtonElement>(
      '.assistant-sidebar-sessions button[data-action="new-chat"]',
    );
    expect(button).not.toBeNull();
    expect(button).toHaveAccessibleName('New chat');
    expect(button).toHaveAttribute('data-omnix-new-chat-coordinator', 'true');

    const originalClick = vi.fn();
    button?.addEventListener('click', originalClick);
    button?.click();

    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    await vi.waitFor(() => expect(selectedSessions).toEqual(['chat:new-session']));

    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe('/api/chat/sessions');
    expect(init).toMatchObject({
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });
    expect(JSON.parse(String(init?.body))).toEqual({ title: 'New chat' });
    expect(originalClick).not.toHaveBeenCalled();
    expect(createdSessions).toHaveLength(1);
    expect(stopEvents).toHaveBeenCalledTimes(1);
    expect(document.querySelector<HTMLTextAreaElement>('textarea[name="content"]')?.value).toBe('');
    expect(button?.disabled).toBe(false);
    expect(button?.hasAttribute('aria-busy')).toBe(false);
  });

  it('restores the New Chat control after the React-owned header is rerendered', async () => {
    const header = document.querySelector<HTMLElement>('.assistant-sidebar-sessions > header');
    expect(header?.querySelectorAll('button')).toHaveLength(1);

    if (header) header.innerHTML = '<h2>Sessions</h2>';

    await vi.waitFor(() => {
      expect(header?.querySelectorAll('button[data-action="new-chat"]')).toHaveLength(1);
    });
  });

  it('does not intercept unrelated buttons outside the sessions panel', () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    const unrelated = document.createElement('button');
    unrelated.textContent = '+ New';
    const clickHandler = vi.fn();
    unrelated.addEventListener('click', clickHandler);
    document.body.appendChild(unrelated);

    unrelated.click();

    expect(clickHandler).toHaveBeenCalledTimes(1);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
