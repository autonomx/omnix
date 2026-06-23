export {
  ASSISTANT_WORKSPACE_SESSION_MODES,
  assertProjectSessionLink,
  assertWorkspaceProjectLink,
  assertWorkspaceSessionLink,
  createChatSessionRef,
  createProjectRef,
  createWorkspaceRef,
  isChatSessionMode,
} from './domain';
export type {
  ChatSession,
  ChatSessionMode,
  ChatSessionRef,
  Project,
  ProjectRef,
  Workspace,
  WorkspaceRef,
} from './domain';

export {
  appendConversationTurn,
  CONVERSATION_TURN_ROLES,
  createConversationTurn,
  getLatestConversationTurn,
  isConversationTurnRole,
} from './conversation';
export type {
  ConversationState,
  ConversationTurn,
  ConversationTurnMetadata,
  ConversationTurnRole,
  MessageContent,
  TokenUsage,
} from './conversation';

export { ASSISTANT_WORKSPACE_EVENT_TYPES, isAssistantWorkspaceEventType } from './events';
export type { AssistantWorkspaceEvent, AssistantWorkspaceEventType } from './events';

export {
  appendProjectionEvent,
  createConversationProjection,
  rebuildConversationProjection,
} from './projections';
export type { ConversationProjection } from './projections';

export { assembleContext, createContextSource, getEnabledInstructions } from './context';
export type {
  AssistantIdentityContext,
  ContextAssembly,
  ContextSource,
  ContextSourceType,
  KnowledgeChunkContext,
  MemoryContext,
  ToolContext,
  WorkspaceInstructionContext,
} from './context';
