import { describe, expect, it } from 'vitest';
import { addTraceEdge, addTraceNode, buildAnswerTraceGraph, createTraceGraph, getUpstreamTraceNodes } from './trace';

describe('trace graph', () => {
  it('links answers to supporting sources and plans', () => {
    const graph = buildAnswerTraceGraph({ answerId: 'answer:1', sourceIds: ['memory:1', 'source:1'], planId: 'plan:1' });
    expect(graph.nodes).toHaveLength(4);
    expect(getUpstreamTraceNodes(graph, 'answer:1').map((node) => node.id)).toEqual(['memory:1', 'source:1', 'plan:1']);
  });

  it('deduplicates nodes and edges', () => {
    const graph = createTraceGraph(
      [{ id: 'a', type: 'answer', label: 'A' }, { id: 'a', type: 'answer', label: 'A2' }],
      [{ from: 'a', to: 'a', relationship: 'cited' }, { from: 'a', to: 'a', relationship: 'cited' }],
    );
    expect(graph.nodes).toHaveLength(1);
    expect(graph.edges).toHaveLength(1);
  });

  it('ignores edges for missing nodes', () => {
    const graph = addTraceNode(createTraceGraph(), { id: 'a', type: 'answer', label: 'A' });
    expect(addTraceEdge(graph, { from: 'missing', to: 'a', relationship: 'triggered' }).edges).toHaveLength(0);
  });
});
