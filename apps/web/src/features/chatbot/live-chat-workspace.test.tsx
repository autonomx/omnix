import { afterEach, describe, expect, it } from 'vitest';

import {
  closeLiveChat,
  installLiveChatNavigation,
  openLiveChat,
  sessionIdFromChatRequest,
} from './live-chat-workspace';

afterEach(() => {
  closeLiveChat();
  document.body.innerHTML = '';
});

describe('live chat workspace controller', () => {
  it('recognizes the selected chat session from session API requests', () => {
    expect(sessionIdFromChatRequest('/api/chat/sessions/chat%3Aone')).toBe('chat:one');
    expect(sessionIdFromChatRequest('/api/chat/sessions/chat%3Aone/live-call/runtime')).toBe('chat:one');
    expect(sessionIdFromChatRequest('/api/chat/sessions')).toBeNull();
  });

  it('adds Live Chat immediately after Chats and mounts one workspace host', () => {
    document.body.innerHTML = `
      <nav class="assistant-sidebar-nav">
        <button type="button"><span>Chats</span></button>
        <button type="button"><span>Voice Sessions</span></button>
      </nav>
      <main class="assistant-chat-main"><div data-existing-view>Chats view</div></main>
    `;

    const button = installLiveChatNavigation();
    expect(button?.textContent).toContain('Live Chat');
    expect(button?.previousElementSibling?.textContent).toContain('Chats');

    openLiveChat();
    expect(document.querySelector('.assistant-chat-main')).toHaveClass('omnix-live-chat-active');
    expect(document.querySelectorAll('[data-omnix-live-chat-host]')).toHaveLength(1);

    openLiveChat();
    expect(document.querySelectorAll('[data-omnix-live-chat-host]')).toHaveLength(1);
  });
});
