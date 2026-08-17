import { QueryClientProvider, type QueryClient } from '@tanstack/react-query';
import { createRoot, type Root } from 'react-dom/client';

import { LiveChatPanel } from './LiveChatPanel';

type LiveChatWindow = Window & typeof globalThis & {
  __omnixLiveChatWorkspaceInstalled?: boolean;
};

type LiveCallDiagnosticDetail = {
  event?: unknown;
  details?: Record<string, unknown>;
};

const NAV_ATTRIBUTE = 'data-omnix-live-chat-nav';
const HOST_ATTRIBUTE = 'data-omnix-live-chat-host';
const SESSION_CHANGED_EVENT = 'omnix:live-chat-session-changed';
const LIVE_CALL_DIAGNOSTIC_EVENT = 'omnix:live-call-diagnostic';
const SESSION_PATH = /^\/api\/chat\/sessions\/([^/]+)(?:$|\/)/;
const SESSION_RECONCILIATION_EVENTS = new Set([
  'turn_finished',
  'turn_stopped',
  'turn_failed_final',
]);

let active = false;
let selectedSessionId: string | null = null;
let mountedRoot: Root | null = null;
let mountedHost: HTMLElement | null = null;
let workspaceQueryClient: QueryClient | null = null;

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

export function initializeLiveChatWorkspace(queryClient: QueryClient): () => void {
  workspaceQueryClient = queryClient;
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
  const handleLiveCallDiagnostic = (event: Event) => {
    const detail = (event as CustomEvent<LiveCallDiagnosticDetail>).detail;
    const eventName = typeof detail?.event === 'string' ? detail.event : '';
    if (!SESSION_RECONCILIATION_EVENTS.has(eventName)) return;
    if (detail?.details?.turn_kind !== 'response') return;
    const sessionId = selectedSessionId;
    const client = workspaceQueryClient;
    if (!sessionId || !client) return;

    // Live voice deliberately avoids projecting a potentially large session
    // while first audio is on the critical path. Reconcile from persisted chat
    // state once the response turn is terminal so interrupted or otherwise
    // deferred turns cannot leave the visible chat one turn behind.
    void client.invalidateQueries({
      queryKey: ['feature', 'chatbot', 'session', sessionId],
      exact: true,
    });
    void client.invalidateQueries({
      queryKey: ['feature', 'chatbot', 'sessions'],
      exact: true,
    });
  };
  const handleNavigationClick = (event: Event) => {
    const button = (event.target as Element | null)?.closest<HTMLButtonElement>('.assistant-sidebar-nav button');
    if (!button || button.hasAttribute(NAV_ATTRIBUTE)) return;
    closeLiveChat();
  };
  window.addEventListener(SESSION_CHANGED_EVENT, handleSessionChanged);
  window.addEventListener(LIVE_CALL_DIAGNOSTIC_EVENT, handleLiveCallDiagnostic);
  document.addEventListener('click', handleNavigationClick, true);
  installLiveChatNavigation();

  return () => {
    observer.disconnect();
    window.removeEventListener(SESSION_CHANGED_EVENT, handleSessionChanged);
    window.removeEventListener(LIVE_CALL_DIAGNOSTIC_EVENT, handleLiveCallDiagnostic);
    document.removeEventListener('click', handleNavigationClick, true);
    closeLiveChat();
    document.querySelector(`[${NAV_ATTRIBUTE}]`)?.remove();
    window.fetch = originalFetch;
    selectedSessionId = null;
    workspaceQueryClient = null;
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
  const liveChatButton = nav?.querySelector<HTMLButtonElement>(`button[${NAV_ATTRIBUTE}]`);
  liveChatButton?.classList.remove('active');
  liveChatButton?.removeAttribute('aria-current');
}

function selectLiveChatNavigation(nav: HTMLElement): void {
  const liveChatButton = nav.querySelector<HTMLButtonElement>(`button[${NAV_ATTRIBUTE}]`);
  nav.querySelectorAll<HTMLButtonElement>('button').forEach((button) => {
    const selected = button === liveChatButton;
    button.classList.toggle('active', selected);
    if (selected) button.setAttribute('aria-current', 'page');
    else button.removeAttribute('aria-current');
  });
}

function renderLiveChat(): void {
  if (!active) return;
  const main = document.querySelector<HTMLElement>('.assistant-chat-main');
  const nav = document.querySelector<HTMLElement>('.assistant-sidebar-nav');
  const queryClient = workspaceQueryClient;
  if (!main || !nav || !queryClient) return;

  main.classList.add('omnix-live-chat-active');
  nav.classList.add('omnix-live-chat-nav-active');
  selectLiveChatNavigation(nav);

  if (!mountedHost || !mountedHost.isConnected) {
    mountedRoot?.unmount();
    mountedHost = document.createElement('div');
    mountedHost.setAttribute(HOST_ATTRIBUTE, 'true');
    main.appendChild(mountedHost);
    mountedRoot = createRoot(mountedHost);
  }
  mountedRoot?.render(
    <QueryClientProvider client={queryClient}>
      <LiveChatPanel sessionId={selectedSessionId} onSessionResolved={(sessionId) => {
        selectedSessionId = sessionId;
        window.dispatchEvent(new CustomEvent(SESSION_CHANGED_EVENT, { detail: { sessionId } }));
        renderLiveChat();
      }} />
    </QueryClientProvider>,
  );
}
