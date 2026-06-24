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

function createEmptyKnowledgeSource(input: Omit<KnowledgeSource, 'retrieve'>): KnowledgeSource {
  return { ...input, retrieve: async () => ({ sourceId: input.id, chunks: [], status: 'empty' }) };
}

export const DEFAULT_KNOWLEDGE_SOURCES = [
  createEmptyKnowledgeSource({ id: 'memory', label: 'Memory', type: 'memory', description: 'Assistant memory and user preferences.', defaultConfig: { enabled: true, priority: 10 } }),
  createEmptyKnowledgeSource({ id: 'workspace_documents', label: 'Workspace Documents', type: 'workspace_document', description: 'Project and workspace documents managed by Omnix.', defaultConfig: { enabled: true, priority: 20 } }),
  createEmptyKnowledgeSource({ id: 'attached_files', label: 'Attached Files', type: 'attached_file', description: 'Files attached to the active conversation or workspace.', defaultConfig: { enabled: true, priority: 30 } }),
  createEmptyKnowledgeSource({ id: 'user_notes', label: 'User Notes', type: 'user_note', description: 'User notes available to the assistant.', defaultConfig: { enabled: true, priority: 40 } }),
  createEmptyKnowledgeSource({ id: 'github_source', label: 'GitHub Source', type: 'github_source', description: 'Read-only repository, pull request, issue, commit, and run-log knowledge.', defaultConfig: { enabled: false, priority: 50 } }),
  createEmptyKnowledgeSource({ id: 'web_research', label: 'Web Search', type: 'web', description: 'Fresh information retrieved as a knowledge source.', defaultConfig: { enabled: false, priority: 80, settings: { mode: 'manual' } } }),
] as const;

export function createDefaultKnowledgeRegistry(): KnowledgeRegistry { return createKnowledgeRegistry([...DEFAULT_KNOWLEDGE_SOURCES]); }
