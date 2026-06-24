export type SourceProfile = { maxItems: number };
export type SourceRequest = { query: string; profile: SourceProfile; plannedQueries: string[] };
export type SourceItem = { id: string; label: string; location: string; summary?: string; score?: number };
export type SourceContent = { id: string; label?: string; location: string; content: string; collectedAt: string };
export type SourceExtract = { id: string; label?: string; location: string; content: string; tokenEstimate: number };

export type SourceAdapter = {
  lookup: (request: SourceRequest) => Promise<SourceItem[]>;
  collect: (location: string) => Promise<SourceContent>;
  extract: (content: SourceContent) => SourceExtract;
};

export function listSourceItems(items: SourceItem[]): SourceItem[] { return [...items]; }

export function createMockSourceAdapter(input: { items?: Record<string, SourceItem[]>; contents?: Record<string, SourceContent> } = {}): SourceAdapter {
  return {
    async lookup(request) {
      const items = request.plannedQueries.flatMap((query) => input.items?.[query] ?? []);
      return rankSourceItems(items, request.profile.maxItems);
    },
    async collect(location) {
      return input.contents?.[location] ?? { id: location, label: location, location, content: '', collectedAt: new Date(0).toISOString() };
    },
    extract(content) {
      const normalized = normalizeSourceContent(content.content);
      return { id: content.id, label: content.label, location: content.location, content: normalized, tokenEstimate: estimateSourceTokens(normalized) };
    },
  };
}

export function rankSourceItems(items: SourceItem[], limit: number): SourceItem[] {
  const deduped = new Map<string, SourceItem>();
  for (const item of items) {
    const current = deduped.get(item.location);
    if (!current || (item.score ?? 0) > (current.score ?? 0)) deduped.set(item.location, item);
  }
  return Array.from(deduped.values()).sort((left, right) => (right.score ?? 0) - (left.score ?? 0)).slice(0, limit);
}

export function estimateSourceTokens(content: string): number { return Math.max(1, Math.ceil(content.trim().length / 4)); }
function normalizeSourceContent(value: string): string { return value.replace(/\s+/g, ' ').trim(); }
