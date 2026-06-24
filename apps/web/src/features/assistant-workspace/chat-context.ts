import { deriveAssistantCapabilities, type AssistantCapability } from './derived-capabilities';
import { createDefaultKnowledgeRegistry, type KnowledgeSourceConfig } from './knowledge-registry';
import { assemblePack, type Pack } from './pack';
import { createDefaultAssistantToolRegistry, type ToolConfig } from './tool-registry';
import { DEFAULT_WEB_RESEARCH_CONFIG, decideWebResearch } from './web-research';
import { createAssistantPlan, type AssistantPlan } from './planning-engine';

export type ChatContextInput = {
  prompt: string;
  workspaceId: string;
  projectId?: string;
  toolConfigs?: Record<string, ToolConfig>;
  sourceConfigs?: Record<string, KnowledgeSourceConfig>;
  providerCapabilities?: AssistantCapability[];
  tokenBudget?: number;
  currentContext?: string[];
};

export type ChatContextPlan = {
  plan: AssistantPlan;
  capabilities: AssistantCapability[];
  pack: Pack;
  retrievalSourceIds: string[];
};

export function createChatContextPlan(input: ChatContextInput): ChatContextPlan {
  const tools = createDefaultAssistantToolRegistry();
  const knowledge = createDefaultKnowledgeRegistry();
  const capabilities = [
    ...deriveAssistantCapabilities({ tools, knowledge, toolConfigs: input.toolConfigs, knowledgeConfigs: input.sourceConfigs }),
    ...(input.providerCapabilities ?? []),
  ];
  const plan = createAssistantPlan({ prompt: input.prompt, capabilities });
  const webEnabled = Boolean(input.sourceConfigs?.web_research?.enabled);
  const webDecision = decideWebResearch(
    { ...DEFAULT_WEB_RESEARCH_CONFIG, enabled: webEnabled, mode: webEnabled ? 'automatic' : 'disabled' },
    { freshnessRequired: plan.retrieval.needsFreshness, verificationRequired: plan.retrieval.needsVerification, explicitRequest: input.prompt.toLowerCase().includes('search') },
  );
  const sourceIds = plan.retrieval.sourceIds.filter((sourceId) => sourceId !== 'web_research' || webDecision.shouldRetrieve);
  const pack = assemblePack({
    query: input.prompt,
    tokenBudget: input.tokenBudget ?? 1_000,
    sources: [
      ...(input.currentContext ?? []).map((content, index) => ({ id: `conversation:${index}`, content, priority: 'conversation' as const, relevance: 1, traceId: `conversation:${index}` })),
      ...sourceIds.map((sourceId) => ({ id: sourceId, content: `Source selected: ${sourceId}`, priority: sourceId === 'web_research' ? 'network' as const : 'source' as const, relevance: 0.6, traceId: `source:${sourceId}` })),
    ],
  });
  return { plan, capabilities, pack, retrievalSourceIds: sourceIds };
}
