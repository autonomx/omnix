import type { AssistantWorkspaceEvent } from './events';
import type { ConversationTurnRole } from './conversation';

export type ChatbotActivityMessage = {
  id: string;
  role: 'system' | 'user' | 'assistant';
  content: string;
  created_at: string;
  metadata?: Record<string, unknown>;
};

export type ChatbotActivitySession = {
  id: string;
  messages?: ChatbotActivityMessage[];
};

export type ChatbotActivityEventOptions = {
  workspaceId: string;
  projectId?: string;
};

export function createChatbotActivityEvents(
  session: ChatbotActivitySession | undefined,
  options: ChatbotActivityEventOptions,
): AssistantWorkspaceEvent[] {
  if (!session?.messages?.length) return [];

  return session.messages
    .filter((message) => message.role === 'user' || message.role === 'assistant')
    .map((message) => createMessageEvent(session.id, message, options));
}

function createMessageEvent(
  sessionId: string,
  message: ChatbotActivityMessage,
  options: ChatbotActivityEventOptions,
): AssistantWorkspaceEvent {
  const base = {
    id: createChatbotActivityEventId(sessionId, message),
    workspaceId: options.workspaceId,
    sessionId,
    createdAt: message.created_at,
    payload: {
      turn: {
        id: message.id,
        sessionId,
        role: message.role as ConversationTurnRole,
        content: [{ kind: 'text' as const, text: message.content }],
        metadata: normalizeMessageMetadata(message.metadata),
        createdAt: message.created_at,
      },
    },
  };

  const event = {
    ...base,
    ...(options.projectId ? { projectId: options.projectId } : {}),
    type: message.role === 'user' ? 'user_message' : 'assistant_message',
  } as const;

  return event as AssistantWorkspaceEvent;
}

function createChatbotActivityEventId(sessionId: string, message: ChatbotActivityMessage): string {
  return `chatbot:${sessionId}:${message.id}:${message.role}`;
}

function normalizeMessageMetadata(metadata: Record<string, unknown> | undefined) {
  return metadata ? { ...metadata } : {};
}
