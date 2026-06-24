import { describe, expect, it } from 'vitest';
import { createDefaultKnowledgeRegistry, createKnowledgeRegistry, type KnowledgeSource } from './knowledge-registry';

describe('assistant workspace knowledge registry', () => {
  it('lists default sources by priority with web as a disabled knowledge source', () => {
    const registry = createDefaultKnowledgeRegistry();
    expect(registry.list().map((source) => source.id)).toEqual(['memory', 'workspace_documents', 'attached_files', 'user_notes', 'github_source', 'web_research']);
    expect(registry.get('web_research')?.type).toBe('web');
    expect(registry.get('web_research')?.defaultConfig.enabled).toBe(false);
  });

  it('retrieves from enabled sources only', async () => {
    const source: KnowledgeSource = {
      id: 'test_docs',
      label: 'Test docs',
      type: 'workspace_document',
      description: 'Test source.',
      defaultConfig: { enabled: true, priority: 1 },
      retrieve: async (request) => ({
        sourceId: 'test_docs',
        status: 'completed',
        chunks: [{ id: 'chunk-1', sourceId: 'test_docs', sourceType: 'workspace_document', content: request.query }],
      }),
    };
    const registry = createKnowledgeRegistry([source]);
    const results = await registry.retrieve({ query: 'architecture', workspaceId: 'omnix' });
    expect(results[0]?.chunks[0]?.content).toBe('architecture');
  });

  it('applies source enablement overrides', () => {
    const registry = createDefaultKnowledgeRegistry();
    const enabled = registry.enabledSources({ web_research: { enabled: true, priority: 80 } });
    expect(enabled.some((source) => source.id === 'web_research')).toBe(true);
  });
});
