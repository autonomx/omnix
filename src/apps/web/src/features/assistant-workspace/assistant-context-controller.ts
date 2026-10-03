import { fetchBelow, registerFetchMiddleware } from '../../api/fetchPipeline';
import {
  adoptActiveSession,
  applySessionResearchMode,
  assistantContextStore,
  deferResearchModePersistence,
  dispatchPerformance,
  loadProfileResearchDefault,
  stopDesktopShare,
  storeLocalWorkspace,
} from './assistant-context-store';
import type { DesktopTemporalCapture } from './desktop-temporal-capture';

export {
  desktopStatusLabel,
  localWorkspaceSummary,
  normalizeDeepResearchPageLimit,
  normalizeLocalWorkspaceSelection,
  normalizeResearchMode,
  readStoredAgentMode,
  webResearchModeLabel,
} from './assistant-context-store';
export type { LocalWorkspaceSelection } from './assistant-context-store';

export type DesktopCompanionCaptureSnapshot = {
  sessionId: string | null;
  characterId: string | null;
  sourceFingerprint: string;
  capture: DesktopTemporalCapture;
};

const MESSAGE_PATH = /^\/api\/chat\/sessions\/([^/]+)\/messages(\/stream)?$/;
const SESSION_PATH = /^\/api\/chat\/sessions\/([^/]+)$/;
const MIDDLEWARE = 'assistant-context';

let disposeController: (() => void) | null = null;

/**
 * Sends chat messages through the context route when a context tool is on
 * (research, agent mode, desktop sharing, a local folder) and follows the
 * session's research mode. The composer renders the controls from
 * assistant-context-store; this installs only the request handling.
 */
export function initializeAssistantContextController(): () => void {
  if (disposeController) return () => undefined;
  assistantContextStore.useFetch(fetchBelow(MIDDLEWARE));
  const removeMiddleware = installFetchInterceptor();
  void loadProfileResearchDefault();
  window.addEventListener('omnix:chat-session-selected', handleChatSessionSelected);
  const handleUnload = () => stopDesktopShare();
  window.addEventListener('beforeunload', handleUnload, { once: true });
  const dispose = () => {
    removeMiddleware();
    assistantContextStore.useFetch(null);
    window.removeEventListener('omnix:chat-session-selected', handleChatSessionSelected);
    window.removeEventListener('beforeunload', handleUnload);
    stopDesktopShare();
    if (disposeController === dispose) disposeController = null;
  };
  disposeController = dispose;
  return dispose;
}

export function isAssistantMessageRequest(url: string, method: string): boolean {
  const parsed = new URL(url, window.location.origin);
  return method.toUpperCase() === 'POST' && MESSAGE_PATH.test(parsed.pathname);
}

export function enhancedAssistantMessageUrl(url: string): string | null {
  const parsed = new URL(url, window.location.origin);
  const match = parsed.pathname.match(MESSAGE_PATH);
  if (!match) return null;
  parsed.pathname = `/api/assistant/context/chat/sessions/${match[1]}/messages${match[2] ?? ''}`;
  return parsed.toString();
}

export function currentDesktopCompanionCapture(): DesktopCompanionCaptureSnapshot | null {
  const { desktopShare, activeSessionId } = assistantContextStore.getState();
  if (!desktopShare) return null;
  return {
    sessionId: activeSessionId,
    characterId: null,
    sourceFingerprint: desktopShare.sourceFingerprint,
    capture: desktopShare.capture,
  };
}

function installFetchInterceptor(): () => void {
  return registerFetchMiddleware(MIDDLEWARE, async (input, init, next) => {
    const method = (init?.method ?? (input instanceof Request ? input.method : 'GET')).toUpperCase();
    const inputUrl = typeof input === 'string' || input instanceof URL ? input.toString() : input.url;
    const parsed = new URL(inputUrl, window.location.origin);
    const sessionMatch = parsed.pathname.match(SESSION_PATH);

    if (method === 'GET' && sessionMatch) {
      const response = await next(input, init);
      if (response.ok) void readSessionResearchMode(decodePathSegment(sessionMatch[1]), response.clone());
      return response;
    }
    if (!isAssistantMessageRequest(inputUrl, method)) return next(input, init);

    const messageMatch = parsed.pathname.match(MESSAGE_PATH);
    adoptActiveSession(messageMatch?.[1] ? decodePathSegment(messageMatch[1]) : null);
    const context = assistantContextStore.getState();
    const { activeSessionId, agentMode, researchMode, desktopShare, localWorkspace } = context;

    if (activeSessionId && localWorkspace) storeLocalWorkspace(activeSessionId, localWorkspace);
    const shouldEnhance = agentMode || researchMode !== 'disabled' || desktopShare !== null || localWorkspace !== null;
    if (!shouldEnhance) {
      const responsePromise = next(input, init);
      deferResearchModePersistence(responsePromise, activeSessionId, researchMode);
      dispatchPerformance('assistant_context_chat_request_dispatched', {
        sessionId: activeSessionId,
        agentMode,
        researchMode,
        enhanced: false,
        persistenceDeferred: true,
      });
      return responsePromise;
    }

    const bodyText = await requestBodyText(input, init);
    let payload: Record<string, unknown>;
    try {
      payload = JSON.parse(bodyText) as Record<string, unknown>;
    } catch {
      const responsePromise = next(input, init);
      deferResearchModePersistence(responsePromise, activeSessionId, researchMode);
      return responsePromise;
    }

    let desktopPayload: Awaited<ReturnType<DesktopTemporalCapture['buildPayload']>> | undefined;
    if (desktopShare) {
      try {
        desktopPayload = await desktopShare.capture.buildPayload();
        assistantContextStore.update({
          desktopStatus: desktopPayload.captureMode === 'temporal'
            ? `${desktopPayload.selectedHistoryFrames} history + current`
            : 'Current frame attached',
        });
      } catch (error) {
        stopDesktopShare({ resetStatus: false });
        assistantContextStore.update({ desktopStatus: error instanceof Error ? error.message : 'Capture failed' });
      }
    }

    const enhancedUrl = enhancedAssistantMessageUrl(inputUrl);
    if (!enhancedUrl) {
      const responsePromise = next(input, init);
      deferResearchModePersistence(responsePromise, activeSessionId, researchMode);
      return responsePromise;
    }
    const headers = new Headers(init?.headers ?? (input instanceof Request ? input.headers : undefined));
    headers.set('Content-Type', 'application/json');
    dispatchPerformance('assistant_context_chat_request_dispatched', {
      sessionId: activeSessionId,
      agentMode,
      researchMode,
      enhanced: true,
      persistenceDeferred: true,
    });
    const enhancedResponse = await next(enhancedUrl, {
      ...init,
      method: 'POST',
      headers,
      body: JSON.stringify({
        ...payload,
        agent_mode: agentMode ? true : payload.agent_mode,
        dry_run: agentMode ? false : payload.dry_run,
        web_research_mode: researchMode,
        deep_research_max_pages: researchMode === 'deep' ? context.deepResearchMaxPages : undefined,
        workspace_root: localWorkspace?.path,
        desktop_current_image_data_url: desktopPayload?.currentImageDataUrl,
        desktop_history_image_data_url: desktopPayload?.historyImageDataUrl,
        desktop_combined_image_data_url: desktopPayload?.combinedImageDataUrl,
        desktop_history_timestamps: desktopPayload?.historyTimestamps ?? [],
        desktop_capture_mode: desktopPayload?.captureMode ?? 'single',
      }),
    });
    if (enhancedResponse.status === 404) {
      const fallbackPromise = next(input, init);
      deferResearchModePersistence(fallbackPromise, activeSessionId, researchMode);
      return fallbackPromise;
    }
    deferResearchModePersistence(Promise.resolve(enhancedResponse), activeSessionId, researchMode);
    return enhancedResponse;
  });
}

async function readSessionResearchMode(sessionId: string, response: Response): Promise<void> {
  try {
    const session = await response.json() as { research_mode_override?: unknown };
    applySessionResearchMode(sessionId, session.research_mode_override);
  } catch {
    // Session reads remain usable when research metadata is absent.
  }
}

function handleChatSessionSelected(event: Event): void {
  adoptActiveSession((event as CustomEvent<{ sessionId?: string | null }>).detail?.sessionId ?? null);
}

async function requestBodyText(input: RequestInfo | URL, init?: RequestInit): Promise<string> {
  if (typeof init?.body === 'string') return init.body;
  if (input instanceof Request) return input.clone().text();
  return '';
}

function decodePathSegment(value: string): string {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}
