export const ASSISTANT_WORKSPACE_EVENT_TYPES = [
  'user_message',
  'assistant_message',
  'tool_call',
  'tool_result',
  'memory_created',
  'memory_recalled',
  'file_attached',
  'knowledge_retrieved',
  'voice_transcript',
  'provider_changed',
  'model_changed',
  'assistant_identity_changed',
  'context_assembled',
] as const;

export type AssistantWorkspaceEventType = (typeof ASSISTANT_WORKSPACE_EVENT_TYPES)[number];

export type AssistantWorkspaceEvent = {
  id: string;
  type: AssistantWorkspaceEventType;
  workspaceId: string;
  projectId?: string;
  sessionId?: string;
  payload: Record<string, unknown>;
  createdAt: string;
};

export function isAssistantWorkspaceEventType(value: string): value is AssistantWorkspaceEventType {
  return ASSISTANT_WORKSPACE_EVENT_TYPES.includes(value as AssistantWorkspaceEventType);
}
