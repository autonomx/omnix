export type PackPriority = 'conversation' | 'workspace' | 'source' | 'memory' | 'result' | 'network' | 'fallback';

export type PackSource = {
  id: string;
  content: string;
  priority: PackPriority;
  relevance: number;
  tokenEstimate?: number;
  traceId?: string;
};

export type PackRequest = { query: string; tokenBudget: number; sources: PackSource[] };
export type Pack = { query: string; sources: PackSource[]; omittedSourceIds: string[]; estimatedTokens: number; traceIds: string[] };
export type PackAssembler = { assemble: (request: PackRequest) => Pack };

const ranks: Record<PackPriority, number> = { conversation: 100, workspace: 90, source: 80, network: 70, memory: 60, result: 50, fallback: 10 };

export function createPackAssembler(): PackAssembler { return { assemble: assemblePack }; }

export function assemblePack(request: PackRequest): Pack {
  const ranked = dedupePackSources(request.sources).sort(comparePackSources);
  const sources: PackSource[] = [];
  const omittedSourceIds: string[] = [];
  let estimatedTokens = 0;
  for (const source of ranked) {
    const sourceTokens = source.tokenEstimate ?? estimatePackTokens(source.content);
    if (estimatedTokens + sourceTokens > request.tokenBudget) { omittedSourceIds.push(source.id); continue; }
    sources.push({ ...source, tokenEstimate: sourceTokens });
    estimatedTokens += sourceTokens;
  }
  return { query: request.query, sources, omittedSourceIds, estimatedTokens, traceIds: sources.flatMap((source) => source.traceId ? [source.traceId] : []) };
}

export function comparePackSources(left: PackSource, right: PackSource): number { return packScore(right) - packScore(left); }
export function packScore(source: PackSource): number { return ranks[source.priority] + source.relevance * 50; }

export function dedupePackSources(sources: PackSource[]): PackSource[] {
  const seen = new Map<string, PackSource>();
  for (const source of sources) {
    const key = source.content.trim().replace(/\s+/g, ' ').toLowerCase();
    const current = seen.get(key);
    if (!current || comparePackSources(source, current) < 0) seen.set(key, source);
  }
  return Array.from(seen.values());
}

export function estimatePackTokens(content: string): number { return Math.max(1, Math.ceil(content.trim().length / 4)); }
