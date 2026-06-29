import { omnixApiClient } from '../../api/client';

const INSTALLED_KEY = '__omnix_chat_session_tools__';
const BUTTON_CLASS = 'omnix-new-chat-button';

type AnyWindow = Window & Record<string, unknown>;

function shouldShowSession(session: { title?: string | null }): boolean {
  return !String(session.title ?? '').trim().startsWith('Podcast script:');
}

function patchSessionList(): void {
  const client = omnixApiClient as unknown as { listChatSessions: typeof omnixApiClient.listChatSessions };
  const original = client.listChatSessions.bind(omnixApiClient);
  client.listChatSessions = async () => {
    const payload = await original();
    return { ...payload, sessions: payload.sessions.filter(shouldShowSession) };
  };
}

async function startBlankChat(): Promise<void> {
  await omnixApiClient.createChatSession({ title: 'New chat' });
  window.location.assign('/chatbot');
}

function addButton(target: Element | null, label: string, prepend = false): void {
  if (!target || target.querySelector(`.${BUTTON_CLASS}`)) return;
  const button = document.createElement('button');
  button.type = 'button';
  button.className = BUTTON_CLASS;
  button.textContent = label;
  button.title = 'Start a clean chat';
  button.addEventListener('click', () => {
    button.setAttribute('disabled', 'true');
    void startBlankChat().catch((error) => {
      button.removeAttribute('disabled');
      console.error('[Omnix] New chat failed', error);
    });
  });
  if (prepend) target.prepend(button);
  else target.appendChild(button);
}

function mountButtons(): void {
  addButton(document.querySelector('.assistant-sidebar-sessions > header'), '+ New');
  addButton(document.querySelector('.assistant-chat-header-actions'), 'New Chat', true);
}

function watchButtons(): void {
  mountButtons();
  const observer = new MutationObserver(mountButtons);
  observer.observe(document.body, { childList: true, subtree: true });
}

export function installSessionTools(): void {
  const w = window as AnyWindow;
  if (w[INSTALLED_KEY]) return;
  w[INSTALLED_KEY] = true;
  patchSessionList();
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', watchButtons, { once: true });
  else watchButtons();
}

installSessionTools();
