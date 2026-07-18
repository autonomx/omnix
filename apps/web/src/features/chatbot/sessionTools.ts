import { omnixApiClient } from '../../api/client';
import type { ChatSession, CreateChatSessionRequest } from '../../api/client';
import './chat-response-metrics-controller.css';
import { initializeChatResponseMetricsController } from './chat-response-metrics-controller';
import { characterClient, type SessionInteraction } from './characterClient';

const INSTALLED_KEY = '__omnix_chat_session_tools__';
const BUTTON_CLASS = 'omnix-new-chat-button';
const MODE_BUTTON_CLASS = 'omnix-chat-mode-button';
const MODE_STORAGE_KEY = 'omnix.chat.mode';
const SESSION_SELECTED_EVENT = 'omnix:chat-session-selected';

type PreservedChatSessionRequest = CreateChatSessionRequest & {
  interaction_mode: 'system' | 'character';
  character_id?: string | null;
  voice_asset_id?: string | null;
  read_memory: boolean;
  write_memory: boolean;
  shared_memory_access: 'none' | 'read_only';
  transcript_policy: 'persistent' | 'temporary' | 'none';
};

let selectedSessionId: string | null = null;

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

export function preservedNewChatRequest(
  session: ChatSession,
  interaction: SessionInteraction,
): PreservedChatSessionRequest {
  return {
    title: 'New chat',
    provider_id: session.provider_id ?? undefined,
    model_id: session.model_id ?? undefined,
    interaction_mode: interaction.interaction_mode,
    character_id: interaction.character_id ?? null,
    voice_asset_id: interaction.voice_asset_id ?? null,
    read_memory: interaction.read_memory,
    write_memory: interaction.write_memory,
    shared_memory_access: interaction.shared_memory_access,
    transcript_policy: interaction.transcript_policy,
  };
}

async function startBlankChat(): Promise<void> {
  let request: CreateChatSessionRequest = { title: 'New chat' };
  if (selectedSessionId) {
    const [session, interaction] = await Promise.all([
      omnixApiClient.getChatSession(selectedSessionId),
      characterClient.session(selectedSessionId),
    ]);
    request = preservedNewChatRequest(session, interaction);
  }
  await omnixApiClient.createChatSession(request);
  window.location.assign('/chatbot');
}

function styleButton(button: HTMLButtonElement): void {
  const compact = button.textContent === '+ New';
  button.style.border = '1px solid rgba(255, 255, 255, 0.16)';
  button.style.borderRadius = compact ? '999px' : '0.65rem';
  button.style.background = 'linear-gradient(135deg, #6544d9, #7c5cff)';
  button.style.color = '#fff';
  button.style.cursor = 'pointer';
  button.style.fontWeight = '750';
  button.style.height = compact ? '2rem' : '2.55rem';
  button.style.minHeight = compact ? '2rem' : '2.55rem';
  button.style.minWidth = compact ? '4.2rem' : '';
  button.style.padding = compact ? '0 0.75rem' : '0 1rem';
  button.style.whiteSpace = 'nowrap';
  button.style.width = 'auto';
}

function updateModeButton(button: HTMLButtonElement): void {
  const enabled = readMode();
  button.textContent = enabled ? 'Agent Chat: On' : 'Agent Chat: Off';
  button.setAttribute('aria-pressed', enabled ? 'true' : 'false');
  button.style.border = '1px solid rgba(255, 255, 255, 0.16)';
  button.style.borderRadius = '0.65rem';
  button.style.background = 'linear-gradient(135deg, #6544d9, #7c5cff)';
  button.style.color = '#fff';
  button.style.cursor = 'pointer';
  button.style.fontWeight = '750';
  button.style.minHeight = '2.55rem';
  button.style.padding = '0 1rem';
}

function addButton(target: Element | null, label: string, prepend = false): void {
  if (!target || target.querySelector(`.${BUTTON_CLASS}`)) return;
  const button = document.createElement('button');
  button.type = 'button';
  button.className = `${BUTTON_CLASS} assistant-header-pill`;
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
  button.className = `${MODE_BUTTON_CLASS} assistant-header-pill`;
  button.addEventListener('click', () => {
    writeMode(!readMode());
    document.querySelectorAll<HTMLButtonElement>(`.${MODE_BUTTON_CLASS}`).forEach(updateModeButton);
  });
  updateModeButton(button);
  target.prepend(button);
}

function mountButtons(): void {
  const headerActions = document.querySelector('.assistant-chat-integrated-actions, .assistant-chat-header-actions');
  addButton(document.querySelector('.assistant-sidebar-sessions > header'), '+ New');
  addButton(headerActions, 'New Chat', true);
  addModeButton(headerActions);
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
  window.addEventListener(SESSION_SELECTED_EVENT, (event) => {
    selectedSessionId = (event as CustomEvent<{ sessionId?: string | null }>).detail?.sessionId ?? null;
  });
  patchSessionList();
  patchSendMessage();
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', watchButtons, { once: true });
  else watchButtons();
}

initializeChatResponseMetricsController();
installSessionTools();
