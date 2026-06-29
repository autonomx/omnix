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

function styleButton(button: HTMLButtonElement): void {
  button.style.border = '1px solid rgba(160, 132, 255, 0.55)';
  button.style.borderRadius = '999px';
  button.style.background = 'rgba(105, 72, 210, 0.24)';
  button.style.color = 'inherit';
  button.style.cursor = 'pointer';
  button.style.fontWeight = '700';
  button.style.padding = '0.42rem 0.7rem';
}

function addButton(target: Element | null, label: string, prepend = false): void {
  if (!target || target.querySelector(`.${BUTTON_CLASS}`)) return;
  const button = document.createElement('button');
  button.type = 'button';
  button.className = BUTTON_CLASS;
  button.textContent = label;
  button.title = 'Start a new chat';
  styleButton(button);
  button.addEventListener('click', () => {
    button.setAttribute('disabled', 'true');
    void startBlankChat().catch(() => {
      button.removeAttribute('disabled');
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
  if (typeof window === 'undefined' || typeof document === 'undefined') return;
  const w = window as unknown as AnyWindow;
  if (w[INSTALLED_KEY]) return;
  w[INSTALLED_KEY] = true;
  patchSessionList();
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', watchButtons, { once: true });
  else watchButtons();
}

installSessionTools();
