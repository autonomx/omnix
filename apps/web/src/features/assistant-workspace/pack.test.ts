import { describe, expect, it } from 'vitest';
import { assemblePack, createPackAssembler, dedupePackSources } from './pack';

describe('assistant workspace pack assembler', () => {
  it('prioritizes workspace sources over memory when relevance ties', () => {
    const pack = assemblePack({
      query: 'project language',
      tokenBudget: 100,
      sources: [
        { id: 'memory', content: 'User prefers Python.', priority: 'memory', relevance: 1 },
        { id: 'workspace', content: 'Current project uses Go.', priority: 'workspace', relevance: 1 },
      ],
    });

    expect(pack.sources[0]?.id).toBe('workspace');
  });

  it('deduplicates repeated content and keeps the higher ranked source', () => {
    const sources = dedupePackSources([
      { id: 'low', content: 'Same fact', priority: 'fallback', relevance: 0.1 },
      { id: 'high', content: 'Same   fact', priority: 'workspace', relevance: 0.9 },
    ]);

    expect(sources).toHaveLength(1);
    expect(sources[0]?.id).toBe('high');
  });

  it('respects token budgets and tracks omitted sources', () => {
    const assembler = createPackAssembler();
    const pack = assembler.assemble({
      query: 'budget',
      tokenBudget: 3,
      sources: [
        { id: 'a', content: '1234', priority: 'workspace', relevance: 1 },
        { id: 'b', content: '12345678901234567890', priority: 'source', relevance: 1 },
      ],
    });

    expect(pack.sources.map((source) => source.id)).toEqual(['a']);
    expect(pack.omittedSourceIds).toEqual(['b']);
  });
});
