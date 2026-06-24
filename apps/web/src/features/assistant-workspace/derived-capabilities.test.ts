import { describe, expect, it } from 'vitest';
import { createDefaultKnowledgeRegistry } from './knowledge-registry';
import { createDefaultAssistantToolRegistry } from './tool-registry';
import { deriveAssistantCapabilities, findCapability } from './derived-capabilities';

describe('derived assistant capabilities', () => {
  it('marks disabled tool capabilities unavailable', () => {
    const capabilities = deriveAssistantCapabilities({ tools: createDefaultAssistantToolRegistry(), knowledge: createDefaultKnowledgeRegistry() });
    expect(findCapability(capabilities, 'gmail.read_email')?.available).toBe(false);
    expect(findCapability(capabilities, 'gmail.read_email')?.reason).toBe('Tool is disabled.');
  });

  it('marks connected enabled read actions available', () => {
    const capabilities = deriveAssistantCapabilities({
      tools: createDefaultAssistantToolRegistry(),
      knowledge: createDefaultKnowledgeRegistry(),
      toolConfigs: { gmail: { enabled: true, connectionStatus: 'connected' } },
    });
    expect(findCapability(capabilities, 'gmail.read_email')?.available).toBe(true);
    expect(findCapability(capabilities, 'gmail.delete_email')?.available).toBe(false);
  });

  it('includes enabled knowledge source capabilities', () => {
    const capabilities = deriveAssistantCapabilities({ tools: createDefaultAssistantToolRegistry(), knowledge: createDefaultKnowledgeRegistry() });
    expect(findCapability(capabilities, 'knowledge.memory')?.available).toBe(true);
  });
});
