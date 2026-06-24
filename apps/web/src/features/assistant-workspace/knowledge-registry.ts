export type KnowledgeSourceType = 'memory' | 'workspace_document' | 'attached_file' | 'user_note' | 'web' | 'external_knowledge_base' | 'github_source';

export type KnowledgeRequest = { query: string; workspaceId: string; projectId?: string; sessionId?: string; maxResults?: number; requestedSourceIds?: string[] };
export type KnowledgeSourceConfig = { enabled: boolean; priority: number; settings?: Record<string, unknown> };
export type KnowledgeChunk = { id: string; sourceId: string; sourceType: KnowledgeSourceType; title?: string; content: string; url?: string; score?: number; tokenEstimate?: number };
export type KnowledgeResult = { sourceId: string; chunks: KnowledgeChunk[]; status: 'completed' | 'empty' | 'failed'; error?: string };

export type KnowledgeSource = {
  id: string;
  label: string;
  type: KnowledgeSourceType;
  description: string;
  defaultConfig: KnowledgeSourceConfig;
  retrieve: (request: KnowledgeRequest, config: KnowledgeSourceConfig) => Promise<KnowledgeResult>;
};

export type KnowledgeRegistry = {
  register: (source: KnowledgeSource) => KnowledgeRegistry;
  list: () => KnowledgeSource[];
  get: (sourceId: string) => KnowledgeSource | undefined;
  enabledSources: (configs?: Record<string, KnowledgeSourceConfig>) => KnowledgeSource[];
  retrieve: (request: KnowledgeRequest, configs?: Record<string, KnowledgeSourceConfig>) => Promise<KnowledgeResult[]>;
};

export function createKnowledgeRegistry(sources: KnowledgeSource[] = []): KnowledgeRegistry {
  const registry = new Map<string, KnowledgeSource>();
  for (const source of sources) registry.set(source.id, source);
  return {
    register(source) { registry.set(source.id, source); return this; },
    list() { return Array.from(registry.values()).sort((left, right) => left.defaultConfig.priority - right.defaultConfig.priority); },
    get(sourceId) { return registry.get(sourceId); },
    enabledSources(configs = {}) { return this.list().filter((source) => (configs[source.id] ?? source.defaultConfig).enabled); },
    async retrieve(request, configs = {}) {
      const selected = this.enabledSources(configs).filter((source) => request.requestedSourceIds?.length ? request.requestedSourceIds.includes(source.id) : true);
      return Promise.all(selected.map((source) => source.retrieve(request, configs[source.id] ?? source.defaultConfig)));
    },
  };
}
