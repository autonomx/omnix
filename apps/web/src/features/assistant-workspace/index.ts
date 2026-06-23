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

export { createProviderCapabilitySet, createStaticModelProvider, providerSupportsRequest } from './provider';
export type { ModelProvider, ModelProviderCapabilities, ModelRequest, ModelResponse } from './provider';

export {
  allocateContextBudget,
  createContextBudgetManager,
  createDefaultContextBudget,
  estimateContextSourceTokens,
} from './budget';
export type { BudgetedContextAssembly, ContextBudget, ContextBudgetManager } from './budget';

export {
  createAssistantResponseAudit,
  explainContextSource,
  summarizeAssistantResponseAudit,
} from './audit';
export type { AssistantResponseAudit, ResponseAuditSummary } from './audit';

export {
  DEFAULT_ASSISTANT_WORKSPACE_PREFERENCES,
  mergeAssistantWorkspacePreferences,
  shouldAnimateWorkspace,
  shouldShowLiveCaptions,
} from './preferences';
export type { AssistantWorkspacePreferences, WorkspaceAppearance, WorkspaceDensity } from './preferences';

export {
  createWorkspaceAccessibilityProfile,
  getResponsivePanelCount,
  isWorkspaceAccessible,
  shouldUseAccessibleMotion,
} from './accessibility';
export type { WorkspaceAccessibilityProfile, WorkspaceBreakpoint } from './accessibility';

export { getWorkspaceQualityStatus, summarizeWorkspaceQuality } from './quality';
export type { WorkspaceQualitySignal, WorkspaceQualitySummary } from './quality';
