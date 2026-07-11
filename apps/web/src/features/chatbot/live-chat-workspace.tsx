import { createRoot, type Root } from 'react-dom/client';

import { LiveChatPanel } from './LiveChatPanel';

type LiveChatWindow = Window & typeof globalThis & {
  __omnixLiveChatWorkspaceInstalled?: boolean;
};

const NAV_ATTRIBUTE = 'data-omnix-live-chat-nav';
const HOST_ATTRIBUTE = 'data-omnix-live-chat-host';
const SESSION_CHANGED_EVENT = 'omnix:live-chat-session-changed';
const SESSION_PATH = /^\/api\/chat\/sessions\/([^/]+)(?:$|\/)/;

let active = false;
let selectedSessionId: string | null = null;
let mountedRoot: Root | null = null;
let mountedHost: HTMLElement | null = null;

export function sessionIdFromChatRequest(input: RequestInfo | URL): string | null {
  const raw = typeof input === 'string' || input instanceof URL ? input.toString() : input.url;
  const pathname = new URL(raw, window.location.origin).pathname;
  const match = SESSION_PATH.exec(pathname);
  if (!match) return null;
  try {
    return decodeURIComponent(match[1]);
  } catch {
    return match[1];
  }
}

export function initializeLiveChatWorkspace(): () => void {
  const liveWindow = window as LiveChatWindow;
  if (liveWindow.__omnixLiveChatWorkspaceInstalled) return () => undefined;
  liveWindow.__omnixLiveChatWorkspaceInstalled = true;

  const originalFetch = window.fetch.bind(window);
  window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const sessionId = sessionIdFromChatRequest(input);
    const response = await originalFetch(input, init);
    if (response.ok && sessionId && sessionId !== selectedSessionId) {
      selectedSessionId = sessionId;
      window.dispatchEvent(new CustomEvent(SESSION_CHANGED_EVENT, { detail: { sessionId } }));
      renderLiveChat();
    }
    return response;
  };

  const observer = new MutationObserver(() => {
    installLiveChatNavigation();
    if (active) renderLiveChat();
  });
  observer.observe(document.documentElement, { childList: true, subtree: true });

  const handleSessionChanged = () => renderLiveChat();
  const handleNavigationClick = (event: Event) => {
    const button = (event.target as Element | null)?.closest<HTMLButtonElement>('.assistant-sidebar-nav button');
    if (!button || button.hasAttribute(NAV_ATTRIBUTE)) return;
    closeLiveChat();
  };
  window.addEventListener(SESSION_CHANGED_EVENT, handleSessionChanged);
  document.addEventListener('click', handleNavigationClick, true);
  installLiveChatNavigation();

  return () => {
    observer.disconnect();
    window.removeEventListener(SESSION_CHANGED_EVENT, handleSessionChanged);
    document.removeEventListener('click', handleNavigationClick, true);
    closeLiveChat();
    document.querySelector(`[${NAV_ATTRIBUTE}]`)?.remove();
    window.fetch = originalFetch;
    liveWindow.__omnixLiveChatWorkspaceInstalled = false;
  };
}

export function installLiveChatNavigation(root: ParentNode = document): HTMLButtonElement | null {
  const nav = root.querySelector<HTMLElement>('.assistant-sidebar-nav');
  if (!nav) return null;
  const existing = nav.querySelector<HTMLButtonElement>(`button[${NAV_ATTRIBUTE}]`);
  if (existing) return existing;

  const button = document.createElement('button');
  button.type = 'button';
  button.setAttribute(NAV_ATTRIBUTE, 'true');
  button.setAttribute('aria-label', 'Open Live Chat view');
  button.title = 'Live Chat';
  const icon = document.createElement('span');
  icon.setAttribute('aria-hidden', 'true');
  icon.textContent = '◉';
  const label = document.createElement('span');
  label.textContent = 'Live Chat';
  button.append(icon, label);
  button.addEventListener('click', () => openLiveChat());

  const chatsButton = nav.querySelector<HTMLButtonElement>('button');
  if (chatsButton?.nextSibling) nav.insertBefore(button, chatsButton.nextSibling);
  else nav.appendChild(button);
  return button;
}

export function openLiveChat(): void {
  active = true;
  renderLiveChat();
}

export function closeLiveChat(): void {
  active = false;
  mountedRoot?.unmount();
  mountedRoot = null;
  mountedHost?.remove();
  mountedHost = null;
  document.querySelector<HTMLElement>('.assistant-chat-main')?.classList.remove('omnix-live-chat-active');
  const nav = document.querySelector<HTMLElement>('.assistant-sidebar-nav');
  nav?.classList.remove('omnix-live-chat-nav-active');
  nav?.querySelector<HTMLButtonElement>(`button[${NAV_ATTRIBUTE}]`)?.classList.remove('active');
}

function renderLiveChat(): void {
  if (!active) return;
  const main = document.querySelector<HTMLElement>('.assistant-chat-main');
  const nav = document.querySelector<HTMLElement>('.assistant-sidebar-nav');
  if (!main || !nav) return;

  main.classList.add('omnix-live-chat-active');
  nav.classList.add('omnix-live-chat-nav-active');
  nav.querySelector<HTMLButtonElement>(`button[${NAV_ATTRIBUTE}]`)?.classList.add('active');

  if (!mountedHost || !mountedHost.isConnected) {
    mountedRoot?.unmount();
    mountedHost = document.createElement('div');
    mountedHost.setAttribute(HOST_ATTRIBUTE, 'true');
    main.appendChild(mountedHost);
    mountedRoot = createRoot(mountedHost);
  }
  mountedRoot?.render(<LiveChatPanel sessionId={selectedSessionId} />);
}
