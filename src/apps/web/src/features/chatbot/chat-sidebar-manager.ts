import { startBlankChat } from './sessionTools';

const HOST_ATTRIBUTE = 'data-omnix-chat-sidebar-manager';
const STORAGE_KEY = 'omnix.chat.sidebar.v1';
const SESSION_SELECTED_EVENT = 'omnix:chat-session-selected';
const LIVE_SESSION_CHANGED_EVENT = 'omnix:live-chat-session-changed';
const SESSION_CREATED_EVENT = 'omnix:chat-session-created';
const REFRESH_DELAY_MS = 80;

type SessionSummary = {
  id: string;
  title?: string | null;
  provider_id?: string | null;
  model_id?: string | null;
  interaction_mode?: 'system' | 'character';
  character_id?: string | null;
  voice_asset_id?: string | null;
  read_memory?: boolean;
  write_memory?: boolean;
  shared_memory_access?: 'none' | 'read_only';
  transcript_policy?: 'persistent' | 'temporary' | 'none';
  message_count?: number;
  created_at?: string;
  updated_at?: string;
};

type SessionListPayload = {
  sessions?: SessionSummary[];
};

type SidebarEntryState = {
  pinned?: boolean;
  archived?: boolean;
  title?: string;
};

type SidebarState = Record<string, SidebarEntryState>;

type SidebarManagerWindow = Window & typeof globalThis & {
  __omnixChatSidebarManagerInstalled?: boolean;
};

let selectedSessionId: string | null = null;
let openMenuSessionId: string | null = null;
let refreshTimer: ReturnType<typeof window.setTimeout> | null = null;
let refreshGeneration = 0;
let sharedSessionFromUrlApplied = false;
let statusTimer: ReturnType<typeof window.setTimeout> | null = null;

export function initializeChatSidebarManager(): () => void {
  if (typeof window === 'undefined' || typeof document === 'undefined') return () => undefined;
  const managerWindow = window as SidebarManagerWindow;
  if (managerWindow.__omnixChatSidebarManagerInstalled) return () => undefined;
  managerWindow.__omnixChatSidebarManagerInstalled = true;

  const handleSessionSelected = (event: Event): void => {
    selectedSessionId = stringValue((event as CustomEvent<{ sessionId?: unknown }>).detail?.sessionId) || null;
    updateActiveRows();
    applySelectedTitleOverride();
  };
  const handleSessionChanged = (event: Event): void => {
    selectedSessionId = stringValue((event as CustomEvent<{ sessionId?: unknown }>).detail?.sessionId) || selectedSessionId;
    scheduleRefresh();
  };
  const handleSessionCreated = (): void => scheduleRefresh();
  const handleFocus = (): void => scheduleRefresh();
  const handleDocumentPointer = (event: Event): void => {
    const target = event.target;
    if (!(target instanceof Node)) return;
    const host = managerHost();
    if (host?.contains(target)) return;
    if (openMenuSessionId) {
      openMenuSessionId = null;
      scheduleRefresh(0);
    }
  };
  const handleKeyDown = (event: KeyboardEvent): void => {
    if (event.key !== 'Escape' || !openMenuSessionId) return;
    openMenuSessionId = null;
    scheduleRefresh(0);
  };

  const observer = new MutationObserver(() => {
    // React updates transcripts, timers, and avatar state throughout a live
    // call. None of those mutations change the session index, and refetching
    // PostgreSQL-backed sessions for each render can starve the audio lane.
    // Observe the document only to install the manager when the sidebar itself
    // is mounted or replaced; explicit session events own data refreshes.
    const sidebar = document.querySelector<HTMLElement>('.assistant-chat-sidebar');
    const host = managerHost();
    if (sidebar && (!host || !sidebar.contains(host))) scheduleRefresh();
  });
  observer.observe(document.documentElement, { childList: true, subtree: true });

  window.addEventListener(SESSION_SELECTED_EVENT, handleSessionSelected);
  window.addEventListener(LIVE_SESSION_CHANGED_EVENT, handleSessionChanged);
  window.addEventListener(SESSION_CREATED_EVENT, handleSessionCreated);
  window.addEventListener('focus', handleFocus);
  document.addEventListener('pointerdown', handleDocumentPointer, true);
  document.addEventListener('keydown', handleKeyDown, true);
  scheduleRefresh(0);

  return () => {
    observer.disconnect();
    window.removeEventListener(SESSION_SELECTED_EVENT, handleSessionSelected);
    window.removeEventListener(LIVE_SESSION_CHANGED_EVENT, handleSessionChanged);
    window.removeEventListener(SESSION_CREATED_EVENT, handleSessionCreated);
    window.removeEventListener('focus', handleFocus);
    document.removeEventListener('pointerdown', handleDocumentPointer, true);
    document.removeEventListener('keydown', handleKeyDown, true);
    if (refreshTimer !== null) window.clearTimeout(refreshTimer);
    if (statusTimer !== null) window.clearTimeout(statusTimer);
    refreshTimer = null;
    statusTimer = null;
    managerHost()?.remove();
    restoreNativeSections();
    selectedSessionId = null;
    openMenuSessionId = null;
    sharedSessionFromUrlApplied = false;
    managerWindow.__omnixChatSidebarManagerInstalled = false;
  };
}

export function readChatSidebarState(): SidebarState {
  try {
    const parsed = JSON.parse(window.localStorage.getItem(STORAGE_KEY) || '{}') as unknown;
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return {};
    return parsed as SidebarState;
  } catch {
    return {};
  }
}

export function writeChatSidebarState(state: SidebarState): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    // Optional browser storage. The current page still reflects the mutation.
  }
}

export function visibleChatSidebarSessions(sessions: SessionSummary[], state: SidebarState): SessionSummary[] {
  return sessions.filter((session) => !state[session.id]?.archived && shouldShowSession(session));
}

export function sortChatSidebarSessions(sessions: SessionSummary[]): SessionSummary[] {
  return [...sessions].sort((left, right) => {
    const rightTime = Date.parse(right.updated_at || right.created_at || '') || 0;
    const leftTime = Date.parse(left.updated_at || left.created_at || '') || 0;
    return rightTime - leftTime;
  });
}

function scheduleRefresh(delayMs = REFRESH_DELAY_MS): void {
  if (refreshTimer !== null) window.clearTimeout(refreshTimer);
  refreshTimer = window.setTimeout(() => {
    refreshTimer = null;
    void refreshSidebar();
  }, delayMs);
}

async function refreshSidebar(): Promise<void> {
  const sidebar = document.querySelector<HTMLElement>('.assistant-chat-sidebar');
  if (!sidebar) return;
  const generation = ++refreshGeneration;
  const host = ensureManagerHost(sidebar);
  hideNativeSections(sidebar);

  let sessions: SessionSummary[] = [];
  try {
    const response = await window.fetch('/api/chat/sessions', {
      method: 'GET',
      headers: { Accept: 'application/json' },
      cache: 'no-store',
    });
    if (!response.ok) throw new Error(`status ${response.status}`);
    const payload = await response.json() as SessionListPayload;
    sessions = Array.isArray(payload.sessions) ? payload.sessions.filter(isSessionSummary) : [];
  } catch (error) {
    if (generation !== refreshGeneration) return;
    renderLoadFailure(host, error);
    return;
  }
  if (generation !== refreshGeneration) return;

  const state = readChatSidebarState();
  const visible = sortChatSidebarSessions(visibleChatSidebarSessions(sessions, state));
  const pinned = visible.filter((session) => state[session.id]?.pinned);
  const regular = visible.filter((session) => !state[session.id]?.pinned);
  host.replaceChildren(
    createPinnedSection(pinned, state),
    createSessionsSection(regular, state),
    createStatusRegion(),
  );
  updateActiveRows();
  applySelectedTitleOverride();
  applySharedSessionFromUrl(visible);
}

function ensureManagerHost(sidebar: HTMLElement): HTMLElement {
  const existing = managerHost();
  if (existing) return existing;
  const host = document.createElement('div');
  host.className = 'assistant-chatgpt-sidebar';
  host.setAttribute(HOST_ATTRIBUTE, 'true');
  const nativeSessions = sidebar.querySelector<HTMLElement>('[aria-labelledby="assistant-chat-sessions"]');
  if (nativeSessions) sidebar.insertBefore(host, nativeSessions);
  else sidebar.appendChild(host);
  return host;
}

function managerHost(): HTMLElement | null {
  return document.querySelector<HTMLElement>(`[${HOST_ATTRIBUTE}="true"]`);
}

function hideNativeSections(sidebar: HTMLElement): void {
  const labelled = [
    'assistant-chat-pinned',
    'assistant-chat-sessions',
    'assistant-chat-recent',
  ];
  for (const id of labelled) {
    const section = sidebar.querySelector<HTMLElement>(`[aria-labelledby="${id}"]`);
    if (!section) continue;
    section.dataset.omnixSidebarNativeHidden = 'true';
    section.hidden = true;
  }
}

function restoreNativeSections(): void {
  document.querySelectorAll<HTMLElement>('[data-omnix-sidebar-native-hidden="true"]').forEach((section) => {
    section.hidden = false;
    delete section.dataset.omnixSidebarNativeHidden;
  });
}

function createPinnedSection(sessions: SessionSummary[], state: SidebarState): HTMLElement {
  const section = createSection('Pinned', 'assistant-chatgpt-pinned');
  const list = section.querySelector<HTMLElement>('.assistant-chatgpt-list');
  if (!list) return section;
  if (!sessions.length) {
    list.appendChild(emptyRow('No pinned chats yet.'));
    return section;
  }
  sessions.forEach((session) => list.appendChild(createSessionRow(session, state, true)));
  return section;
}

function createSessionsSection(sessions: SessionSummary[], state: SidebarState): HTMLElement {
  const section = createSection('Sessions', 'assistant-chatgpt-sessions');
  const header = section.querySelector<HTMLElement>('header');
  if (header) header.appendChild(createNewChatButton());
  const list = section.querySelector<HTMLElement>('.assistant-chatgpt-list');
  if (!list) return section;
  if (!sessions.length) {
    list.appendChild(emptyRow('No other chat sessions.'));
    return section;
  }
  sessions.forEach((session) => list.appendChild(createSessionRow(session, state, false)));
  return section;
}

function createSection(title: string, labelledBy: string): HTMLElement {
  const section = document.createElement('section');
  section.className = 'assistant-chatgpt-section';
  section.setAttribute('aria-labelledby', labelledBy);
  const header = document.createElement('header');
  const heading = document.createElement('h2');
  heading.id = labelledBy;
  heading.textContent = title;
  header.appendChild(heading);
  const list = document.createElement('div');
  list.className = 'assistant-chatgpt-list';
  section.append(header, list);
  return section;
}

function createNewChatButton(): HTMLButtonElement {
  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'assistant-chatgpt-new';
  button.setAttribute('aria-label', 'New chat');
  button.title = 'New chat';
  button.innerHTML = '<span aria-hidden="true">＋</span><span>New</span>';
  button.addEventListener('click', () => {
    const originalContent = button.innerHTML;
    button.disabled = true;
    button.setAttribute('aria-busy', 'true');
    button.setAttribute('aria-label', 'Creating new chat');
    const label = button.querySelector('span:last-child');
    if (label) label.textContent = 'Creating...';
    showSidebarStatus('Creating new chat...');
    void startBlankChat().catch((error) => {
      button.disabled = false;
      button.removeAttribute('aria-busy');
      button.setAttribute('aria-label', 'New chat');
      button.innerHTML = originalContent;
      showSidebarStatus(error instanceof Error ? error.message : 'New chat could not be created.', true);
    });
  });
  return button;
}

function createSessionRow(session: SessionSummary, state: SidebarState, pinned: boolean): HTMLElement {
  const entryState = state[session.id] ?? {};
  const row = document.createElement('div');
  row.className = 'assistant-chatgpt-row';
  row.dataset.sessionId = session.id;
  if (session.id === selectedSessionId) row.classList.add('active');

  const select = document.createElement('button');
  select.type = 'button';
  select.className = 'assistant-chatgpt-session';
  select.title = displayTitle(session, entryState);
  const title = document.createElement('span');
  title.className = 'assistant-chatgpt-title';
  title.textContent = displayTitle(session, entryState);
  select.appendChild(title);
  select.addEventListener('click', () => selectSession(session));

  const actions = document.createElement('div');
  actions.className = 'assistant-chatgpt-actions';
  const pin = document.createElement('button');
  pin.type = 'button';
  pin.className = pinned ? 'assistant-chatgpt-pin pinned' : 'assistant-chatgpt-pin';
  pin.setAttribute('aria-label', pinned ? `Unpin ${displayTitle(session, entryState)}` : `Pin ${displayTitle(session, entryState)}`);
  pin.title = pinned ? 'Unpin chat' : 'Pin chat';
  pin.textContent = '⌖';
  pin.addEventListener('click', () => togglePinned(session.id));

  const more = document.createElement('button');
  more.type = 'button';
  more.className = 'assistant-chatgpt-more';
  more.setAttribute('aria-label', `More options for ${displayTitle(session, entryState)}`);
  more.setAttribute('aria-expanded', openMenuSessionId === session.id ? 'true' : 'false');
  more.title = 'More options';
  more.textContent = '•••';
  more.addEventListener('click', () => {
    openMenuSessionId = openMenuSessionId === session.id ? null : session.id;
    scheduleRefresh(0);
  });
  actions.append(pin, more);
  row.append(select, actions);
  if (openMenuSessionId === session.id) row.appendChild(createSessionMenu(session, entryState, pinned));
  return row;
}

function createSessionMenu(session: SessionSummary, entryState: SidebarEntryState, pinned: boolean): HTMLElement {
  const menu = document.createElement('div');
  menu.className = 'assistant-chatgpt-menu';
  menu.setAttribute('role', 'menu');
  menu.append(
    menuItem('⇧', 'Share', () => void shareSession(session, entryState)),
    menuItem('✎', 'Rename', () => renameSession(session, entryState)),
    menuItem('⌖', pinned ? 'Unpin chat' : 'Pin chat', () => togglePinned(session.id)),
    menuItem('▣', 'Archive', () => archiveSession(session.id)),
    menuItem('⌫', 'Delete', () => void deleteSession(session), true),
  );
  return menu;
}

function menuItem(icon: string, label: string, action: () => void, danger = false): HTMLButtonElement {
  const button = document.createElement('button');
  button.type = 'button';
  button.className = danger ? 'danger' : '';
  button.setAttribute('role', 'menuitem');
  const iconNode = document.createElement('span');
  iconNode.className = 'assistant-chatgpt-menu-icon';
  iconNode.setAttribute('aria-hidden', 'true');
  iconNode.textContent = icon;
  const labelNode = document.createElement('span');
  labelNode.textContent = label;
  button.append(iconNode, labelNode);
  button.addEventListener('click', (event) => {
    event.stopPropagation();
    openMenuSessionId = null;
    action();
  });
  return button;
}

function togglePinned(sessionId: string): void {
  const state = readChatSidebarState();
  const current = state[sessionId] ?? {};
  state[sessionId] = { ...current, pinned: !current.pinned, archived: false };
  writeChatSidebarState(state);
  scheduleRefresh(0);
}

function archiveSession(sessionId: string): void {
  const state = readChatSidebarState();
  const current = state[sessionId] ?? {};
  state[sessionId] = { ...current, archived: true, pinned: false };
  writeChatSidebarState(state);
  if (selectedSessionId === sessionId) selectedSessionId = null;
  showSidebarStatus('Chat archived.');
  scheduleRefresh(0);
}

function renameSession(session: SessionSummary, entryState: SidebarEntryState): void {
  const next = window.prompt('Rename chat', displayTitle(session, entryState));
  if (next === null) return;
  const title = next.trim();
  if (!title) return;
  const state = readChatSidebarState();
  state[session.id] = { ...(state[session.id] ?? {}), title };
  writeChatSidebarState(state);
  applySelectedTitleOverride();
  scheduleRefresh(0);
}

async function shareSession(session: SessionSummary, entryState: SidebarEntryState): Promise<void> {
  const url = new URL('/chatbot', window.location.origin);
  url.searchParams.set('chat_session', session.id);
  const title = displayTitle(session, entryState);
  try {
    if (typeof navigator.share === 'function') {
      await navigator.share({ title, url: url.toString() });
      showSidebarStatus('Share sheet opened.');
      return;
    }
    await navigator.clipboard.writeText(url.toString());
    showSidebarStatus('Chat link copied.');
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') return;
    showSidebarStatus('Could not share this chat.', true);
  }
}

async function deleteSession(session: SessionSummary): Promise<void> {
  const title = displayTitle(session, readChatSidebarState()[session.id] ?? {});
  if (!window.confirm(`Delete "${title}"? This permanently removes the chat history.`)) return;
  try {
    const response = await window.fetch(`/api/chat/sessions/${encodeURIComponent(session.id)}`, { method: 'DELETE' });
    if (!response.ok) throw new Error(`status ${response.status}`);
    const state = readChatSidebarState();
    delete state[session.id];
    writeChatSidebarState(state);
    if (selectedSessionId === session.id) selectedSessionId = null;
    showSidebarStatus('Chat deleted.');
    scheduleRefresh(0);
  } catch {
    showSidebarStatus('Chat could not be deleted.', true);
  }
}

function selectSession(session: SessionSummary): void {
  selectedSessionId = session.id;
  document.querySelector<HTMLButtonElement>('.assistant-sidebar-nav button[aria-label="Open Chats view"]')?.click();
  window.dispatchEvent(new CustomEvent(LIVE_SESSION_CHANGED_EVENT, { detail: { sessionId: session.id } }));
  window.dispatchEvent(new CustomEvent(SESSION_SELECTED_EVENT, { detail: { sessionId: session.id, session } }));
  updateActiveRows();
  applySelectedTitleOverride();
}

function updateActiveRows(): void {
  document.querySelectorAll<HTMLElement>('.assistant-chatgpt-row[data-session-id]').forEach((row) => {
    row.classList.toggle('active', row.dataset.sessionId === selectedSessionId);
  });
}

function applySelectedTitleOverride(): void {
  if (!selectedSessionId) return;
  const title = readChatSidebarState()[selectedSessionId]?.title?.trim();
  if (!title) return;
  const heading = document.querySelector<HTMLElement>('.assistant-chat-header h2');
  if (heading) heading.textContent = title;
}

function applySharedSessionFromUrl(sessions: SessionSummary[]): void {
  if (sharedSessionFromUrlApplied) return;
  const sessionId = new URLSearchParams(window.location.search).get('chat_session')?.trim() ?? '';
  if (!sessionId) {
    sharedSessionFromUrlApplied = true;
    return;
  }
  const session = sessions.find((candidate) => candidate.id === sessionId);
  if (!session) return;
  sharedSessionFromUrlApplied = true;
  selectSession(session);
}

function createStatusRegion(): HTMLElement {
  const status = document.createElement('div');
  status.className = 'assistant-chatgpt-status';
  status.setAttribute('role', 'status');
  status.setAttribute('aria-live', 'polite');
  return status;
}

function showSidebarStatus(message: string, danger = false): void {
  const status = document.querySelector<HTMLElement>('.assistant-chatgpt-status');
  if (!status) return;
  status.textContent = message;
  status.classList.toggle('danger', danger);
  status.classList.add('visible');
  if (statusTimer !== null) window.clearTimeout(statusTimer);
  statusTimer = window.setTimeout(() => {
    status.classList.remove('visible', 'danger');
    status.textContent = '';
    statusTimer = null;
  }, 6000);
}

function renderLoadFailure(host: HTMLElement, error: unknown): void {
  const section = createSection('Sessions', 'assistant-chatgpt-sessions');
  const header = section.querySelector<HTMLElement>('header');
  if (header) header.appendChild(createNewChatButton());
  const list = section.querySelector<HTMLElement>('.assistant-chatgpt-list');
  if (list) list.appendChild(emptyRow(error instanceof Error ? 'Chat sessions failed to load.' : 'Chat sessions unavailable.'));
  host.replaceChildren(section, createStatusRegion());
}

function emptyRow(message: string): HTMLElement {
  const row = document.createElement('p');
  row.className = 'assistant-chatgpt-empty';
  row.textContent = message;
  return row;
}

function displayTitle(session: SessionSummary, entryState: SidebarEntryState): string {
  return entryState.title?.trim() || session.title?.trim() || 'Untitled chat';
}

function shouldShowSession(session: SessionSummary): boolean {
  return !String(session.title ?? '').trim().startsWith('Podcast script:');
}

function isSessionSummary(value: unknown): value is SessionSummary {
  if (!value || typeof value !== 'object') return false;
  const record = value as Record<string, unknown>;
  return typeof record.id === 'string' && record.id.trim().length > 0;
}

function stringValue(value: unknown): string {
  return typeof value === 'string' ? value.trim() : '';
}
