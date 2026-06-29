import { omnixApiClient } from '../../api/client';

const INSTALLED_KEY = '__omnix_chat_session_tools__';
const BUTTON_CLASS = 'omnix-new-chat-button';
const MODE_BUTTON_CLASS = 'omnix-chat-mode-button';
const MODE_STORAGE_KEY = 'omnix.chat.mode';

type AnyWindow = Window & Record<string, unknown>;

type ClientPatch = {
  listChatSessions: typeof omnixApiClient.listChatSessions;
  sendChatMessage: typeof omnixApiClient.sendChatMessage;
};

function shouldShowSession(session: { title?: string | null }): boolean {
  return !String(session.title ?? '').trim().startsWith('Podcast script:');
}

function readMode(): boolean {
  try {
    return window.localStorage.getItem(MODE_STORAGE_KEY) === 'agent';
  } catch {
    return false;
  }
}

function writeMode(enabled: boolean): void {
  try {
    window.localStorage.setItem(MODE_STORAGE_KEY, enabled ? 'agent' : 'normal');
  } catch {
    // optional browser storage
  }
}

function patchSessionList(): void {
  const client = omnixApiClient as unknown as ClientPatch;
  const original = client.listChatSessions.bind(omnixApiClient);
  client.listChatSessions = async () => {
    const payload = await original();
    return { ...payload, sessions: payload.sessions.filter(shouldShowSession) };
  };
}

function patchSendMessage(): void {
  const client = omnixApiClient as unknown as ClientPatch;
  const original = client.sendChatMessage.bind(omnixApiClient);
  client.sendChatMessage = async (sessionId, request) => {
    if (!readMode()) return original(sessionId, request);
    return original(sessionId, { ...(request as Record<string, unknown>), agent_mode: true, dry_run: false } as never);
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

function updateModeButton(button: HTMLButtonElement): void {
  const enabled = readMode();
  button.textContent = enabled ? 'Agent Chat: On' : 'Agent Chat: Off';
  button.setAttribute('aria-pressed', enabled ? 'true' : 'false');
  button.style.border = enabled ? '1px solid rgba(94, 234, 212, 0.75)' : '1px solid rgba(255, 255, 255, 0.18)';
  button.style.borderRadius = '999px';
  button.style.background = enabled ? 'rgba(20, 184, 166, 0.22)' : 'rgba(255, 255, 255, 0.08)';
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

function addModeButton(target: Element | null): void {
  if (!target || target.querySelector(`.${MODE_BUTTON_CLASS}`)) return;
  const button = document.createElement('button');
  button.type = 'button';
  button.className = MODE_BUTTON_CLASS;
  button.addEventListener('click', () => {
    writeMode(!readMode());
    document.querySelectorAll<HTMLButtonElement>(`.${MODE_BUTTON_CLASS}`).forEach(updateModeButton);
  });
  updateModeButton(button);
  target.prepend(button);
}

function mountButtons(): void {
  const headerActions = document.querySelector('.assistant-chat-header-actions');
  addButton(document.querySelector('.assistant-sidebar-sessions > header'), '+ New');
  addButton(headerActions, 'New Chat', true);
  addModeButton(headerActions);
  addModeButton(document.querySelector('.assistant-composer-controls'));
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
  patchSendMessage();
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', watchButtons, { once: true });
  else watchButtons();
}

installSessionTools();
