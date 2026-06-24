import { canExecuteToolAction } from './tool-actions';
import type { ToolConfig } from './tool-registry';
import type { AssistantToolRegistry } from './tool-registry';
import type { KnowledgeRegistry, KnowledgeSourceConfig } from './knowledge-registry';

export type AssistantCapabilitySource = 'tool' | 'knowledge' | 'provider' | 'runtime';

export type AssistantCapability = {
  id: string;
  label: string;
  source: AssistantCapabilitySource;
  available: boolean;
  reason?: string;
  riskLevel?: 'low' | 'medium' | 'high';
};

export type ProviderFeature = {
  id: string;
  label: string;
  available: boolean;
  reason?: string;
};

export type RuntimeFeature = {
  id: string;
  label: string;
  available: boolean;
  reason?: string;
};

export type CapabilityRegistryInput = {
  tools: AssistantToolRegistry;
  knowledge: KnowledgeRegistry;
  toolConfigs?: Record<string, ToolConfig>;
  knowledgeConfigs?: Record<string, KnowledgeSourceConfig>;
  providerFeatures?: ProviderFeature[];
  runtimeFeatures?: RuntimeFeature[];
};

export function deriveAssistantCapabilities(input: CapabilityRegistryInput): AssistantCapability[] {
  return [
    ...deriveToolCapabilities(input),
    ...deriveKnowledgeCapabilities(input),
    ...(input.providerFeatures ?? []).map((feature) => ({ ...feature, source: 'provider' as const })),
    ...(input.runtimeFeatures ?? []).map((feature) => ({ ...feature, source: 'runtime' as const })),
  ];
}

export function getAvailableCapabilities(capabilities: AssistantCapability[]): AssistantCapability[] {
  return capabilities.filter((capability) => capability.available);
}

export function findCapability(capabilities: AssistantCapability[], capabilityId: string): AssistantCapability | undefined {
  return capabilities.find((capability) => capability.id === capabilityId);
}

function deriveToolCapabilities(input: CapabilityRegistryInput): AssistantCapability[] {
  return input.tools.list().flatMap((tool) => {
    const config = input.toolConfigs?.[tool.id] ?? tool.defaultConfig;
    return tool.actions.map((action) => {
      const gate = canExecuteToolAction(action);
      const connected = !action.requiresConnection || config.connectionStatus === 'connected';
      const available = config.enabled && connected && gate.allowed;
      return {
        id: action.id,
        label: action.label,
        source: 'tool' as const,
        available,
        reason: available ? undefined : capabilityUnavailableReason(config.enabled, connected, gate.reason),
        riskLevel: action.riskLevel,
      };
    });
  });
}

function deriveKnowledgeCapabilities(input: CapabilityRegistryInput): AssistantCapability[] {
  return input.knowledge.list().map((source) => {
    const config = input.knowledgeConfigs?.[source.id] ?? source.defaultConfig;
    return {
      id: `knowledge.${source.id}`,
      label: source.label,
      source: 'knowledge' as const,
      available: config.enabled,
      reason: config.enabled ? undefined : 'Knowledge source is disabled.',
    };
  });
}

function capabilityUnavailableReason(enabled: boolean, connected: boolean, gateReason?: string): string {
  if (!enabled) return 'Tool is disabled.';
  if (!connected) return 'Required connection is not configured.';
  return gateReason ?? 'Capability is unavailable.';
}
