export type CapabilityScope = 'global' | 'workspace' | 'project' | 'session';
export type CapabilityEvent = 'registered' | 'enabled' | 'requested' | 'approved' | 'denied' | 'running' | 'completed';

export type CapabilityDefinition = {
  id: string;
  name: string;
  description: string;
  scope: CapabilityScope;
  enabled: boolean;
};

export function createCapabilityDefinition(definition: CapabilityDefinition): CapabilityDefinition {
  return { ...definition };
}

export function getEnabledCapabilities(definitions: CapabilityDefinition[]): CapabilityDefinition[] {
  return definitions.filter((definition) => definition.enabled);
}

export function canUseCapability(definition: CapabilityDefinition, scope: CapabilityScope): boolean {
  return definition.enabled && (definition.scope === 'global' || definition.scope === scope);
}
