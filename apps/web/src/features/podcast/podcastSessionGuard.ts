import { omnixApiClient } from '../../api/client';

const INSTALLED_KEY = '__omnix_podcast_session_guard__';
const DRAFT_PREFIX = 'podcast-draft:';

type AnyWindow = Window & Record<string, unknown>;

type ClientPatch = {
  createChatSession: typeof omnixApiClient.createChatSession;
  sendChatMessage: typeof omnixApiClient.sendChatMessage;
};

function isPodcastDraftTitle(title: unknown): boolean {
  return String(title ?? '').trim().startsWith('Podcast script:');
}

function now(): string {
  return new Date().toISOString();
}

export function installPodcastSessionGuard(): void {
  if (typeof window === 'undefined') return;
  const w = window as AnyWindow;
  if (w[INSTALLED_KEY]) return;
  w[INSTALLED_KEY] = true;

  const client = omnixApiClient as unknown as ClientPatch;
  const originalCreate = client.createChatSession.bind(omnixApiClient);
  const originalSend = client.sendChatMessage.bind(omnixApiClient);

  client.createChatSession = async (request) => {
    if (!isPodcastDraftTitle(request.title)) return originalCreate(request);
    const timestamp = now();
    return {
      id: `${DRAFT_PREFIX}${Date.now()}`,
      title: request.title || 'Podcast script',
      provider_id: request.provider_id ?? null,
      model_id: request.model_id ?? null,
      message_count: 0,
      messages: [],
      created_at: timestamp,
      updated_at: timestamp,
    };
  };

  client.sendChatMessage = async (sessionId, request) => {
    if (!sessionId.startsWith(DRAFT_PREFIX)) return originalSend(sessionId, request);
    const timestamp = now();
    const userMessage = {
      id: `msg:${Date.now()}`,
      role: 'user' as const,
      content: request.content,
      created_at: timestamp,
      metadata: { source: 'podcast_workspace_draft' },
    };
    return {
      session: {
        id: sessionId,
        title: 'Podcast script draft',
        provider_id: request.provider_id ?? null,
        model_id: request.model_id ?? null,
        message_count: 1,
        messages: [userMessage],
        created_at: timestamp,
        updated_at: timestamp,
      },
      user_message: userMessage,
      job: {
        id: `${DRAFT_PREFIX}local`,
        module: 'podcast',
        type: 'script.draft',
        resource_class: 'cpu',
        priority: 0,
        status: 'completed',
        input_ref: {},
        input_payload: {},
        output_refs: [],
        logs: [],
        stages: [],
        error: null,
        created_at: timestamp,
        updated_at: timestamp,
      },
      generation_status: 'queued' as const,
      content: '',
    } as never;
  };
}

installPodcastSessionGuard();
