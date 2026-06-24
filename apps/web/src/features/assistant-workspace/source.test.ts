import { describe, expect, it } from 'vitest';
import { createMockSourceAdapter, estimateSourceTokens, rankSourceItems } from './source';

describe('source adapter', () => {
  it('ranks and deduplicates lookup items', () => {
    const ranked = rankSourceItems([
      { id: 'a', label: 'A', location: 'same', score: 0.1 },
      { id: 'b', label: 'B', location: 'same', score: 0.9 },
      { id: 'c', label: 'C', location: 'other', score: 0.5 },
    ], 2);

    expect(ranked.map((item) => item.id)).toEqual(['b', 'c']);
  });

  it('uses mock fixtures for lookup and collection', async () => {
    const adapter = createMockSourceAdapter({
      items: { omnix: [{ id: 'one', label: 'One', location: 'loc:one', score: 1 }] },
      contents: { 'loc:one': { id: 'one', label: 'One', location: 'loc:one', content: 'Source content', collectedAt: '2026-01-01T00:00:00.000Z' } },
    });

    const items = await adapter.lookup({ query: 'omnix', plannedQueries: ['omnix'], profile: { maxItems: 3 } });
    const content = await adapter.collect(items[0]?.location ?? '');
    const extracted = adapter.extract(content);

    expect(items).toHaveLength(1);
    expect(extracted.content).toBe('Source content');
    expect(extracted.tokenEstimate).toBe(estimateSourceTokens('Source content'));
  });
});
