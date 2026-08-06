type CreatedChatSession = {
  id?: unknown;
  [key: string]: unknown;
};

const LIVE_CHAT_SESSION_CHANGED_EVENT = 'omnix:live-chat-session-changed';
const CHAT_SESSION_CREATED_EVENT = 'omnix:chat-session-created';
const NEW_CHAT_FAILED_EVENT = 'omnix:new-chat-failed';
const LIVE_VOICE_STOP_EVENT = 'omnix:assistant-live-voice-stop';
const GENERATED_BUTTON_ATTRIBUTE = 'data-omnix-new-chat-coordinator';

let installed = false;
let inFlight = false;
let disposeListener: (() => void) | null = null;
let sessionsObserver: MutationObserver | null = null;

function normalizedButtonLabel(button: HTMLButtonElement): string {
  return String(button.getAttribute('aria-label') || button.textContent || '')
    .replace(/\s+/g, ' ')
    .trim()
    .toLocaleLowerCase();
}

function isNewChatButton(button: HTMLButtonElement): boolean {
  const label = normalizedButtonLabel(button);
  const explicitAction = button.dataset.action === 'new-chat' || button.dataset.newChat === 'true';
  const recognizableLabel = label === '+ new' || label === 'new' || label === 'new chat' || label === '+ new chat';
  return explicitAction || recognizableLabel;
}

function newChatButton(target: EventTarget | null): HTMLButtonElement | null {
  if (!(target instanceof Element)) return null;
  const button = target.closest<HTMLButtonElement>('button');
  if (!button || !button.closest('.assistant-sidebar-sessions')) return null;
  return isNewChatButton(button) ? button : null;
}

function ensureNewChatButton(): HTMLButtonElement | null {
  const header = document.querySelector<HTMLElement>('.assistant-sidebar-sessions > header');
  if (!header) return null;

  const existing = [...header.querySelectorAll<HTMLButtonElement>('button')]
    .find((button) => isNewChatButton(button));
  if (existing) return existing;

  const button = document.createElement('button');
  button.type = 'button';
  button.dataset.action = 'new-chat';
  button.dataset.newChat = 'true';
  button.setAttribute(GENERATED_BUTTON_ATTRIBUTE, 'true');
  button.setAttribute('aria-label', 'New chat');
  button.textContent = '+ New';
  header.appendChild(button);
  return button;
}

function clearMessageComposer(): void {
  const textarea = document.querySelector<HTMLTextAreaElement>(
    '.assistant-message-input textarea[name="content"], textarea[placeholder^="Message Omnix"]',
  );
  if (!textarea) return;

  const valueSetter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')?.set;
  if (valueSetter) valueSetter.call(textarea, '');
  else textarea.value = '';
  textarea.dispatchEvent(new Event('input', { bubbles: true }));
  textarea.dispatchEvent(new Event('change', { bubbles: true }));
}

function requestSessionListRefresh(): void {
  document.dispatchEvent(new Event('visibilitychange'));
  window.dispatchEvent(new Event('focus'));
}

async function createAndSelectNewChat(button: HTMLButtonElement): Promise<void> {
  if (inFlight) return;
  inFlight = true;
  const wasDisabled = button.disabled;
  button.disabled = true;
  button.setAttribute('aria-busy', 'true');

  try {
    const response = await window.fetch('/api/chat/sessions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: 'New chat' }),
    });
    if (!response.ok) {
      throw new Error(`New chat request failed with status ${response.status}.`);
    }

    const session = await response.json() as CreatedChatSession;
    const sessionId = typeof session.id === 'string' ? session.id.trim() : '';
    if (!sessionId) throw new Error('New chat response did not include a session id.');

    window.dispatchEvent(new CustomEvent(LIVE_VOICE_STOP_EVENT));
    clearMessageComposer();
    window.dispatchEvent(new CustomEvent(CHAT_SESSION_CREATED_EVENT, { detail: { session } }));
    window.dispatchEvent(new CustomEvent(LIVE_CHAT_SESSION_CHANGED_EVENT, {
      detail: { sessionId },
    }));
    requestSessionListRefresh();
  } catch (error) {
    window.dispatchEvent(new CustomEvent(NEW_CHAT_FAILED_EVENT, {
      detail: { message: error instanceof Error ? error.message : 'New chat could not be created.' },
    }));
    console.error('[Omnix Chat] New chat creation failed.', error);
  } finally {
    inFlight = false;
    button.disabled = wasDisabled;
    button.removeAttribute('aria-busy');
  }
}

export function initializeNewChatCoordinator(): () => void {
  if (typeof window === 'undefined' || typeof document === 'undefined') return () => undefined;
  if (installed) return disposeListener ?? (() => undefined);
  installed = true;

  const handleClick = (event: MouseEvent): void => {
    const button = newChatButton(event.target);
    if (!button) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    void createAndSelectNewChat(button);
  };

  document.addEventListener('click', handleClick, true);
  ensureNewChatButton();
  if (typeof MutationObserver !== 'undefined') {
    sessionsObserver = new MutationObserver(() => ensureNewChatButton());
    sessionsObserver.observe(document.body ?? document.documentElement, {
      childList: true,
      subtree: true,
    });
  }

  disposeListener = () => {
    document.removeEventListener('click', handleClick, true);
    sessionsObserver?.disconnect();
    sessionsObserver = null;
    document.querySelectorAll<HTMLElement>(`[${GENERATED_BUTTON_ATTRIBUTE}="true"]`)
      .forEach((button) => button.remove());
    installed = false;
    inFlight = false;
    disposeListener = null;
  };
  return disposeListener;
}

/** Test-only reset. Runtime callers should keep the coordinator installed. */
export function resetNewChatCoordinatorForTests(): void {
  disposeListener?.();
  sessionsObserver?.disconnect();
  sessionsObserver = null;
  installed = false;
  inFlight = false;
  disposeListener = null;
}
