export type TraceNodeType = 'answer' | 'memory' | 'document' | 'issue' | 'pull_request' | 'source' | 'result' | 'plan';
export type TraceRelationship = 'cited' | 'informed_by' | 'conflicts_with' | 'supersedes' | 'retrieved_for' | 'triggered' | 'executed_by';

export type TraceNode = { id: string; type: TraceNodeType; label: string; ref?: string; metadata?: Record<string, unknown> };
export type TraceEdge = { from: string; to: string; relationship: TraceRelationship };
export type TraceGraph = { nodes: TraceNode[]; edges: TraceEdge[] };

export function createTraceGraph(nodes: TraceNode[] = [], edges: TraceEdge[] = []): TraceGraph {
  return { nodes: dedupeNodes(nodes), edges: dedupeEdges(edges) };
}

export function addTraceNode(graph: TraceGraph, node: TraceNode): TraceGraph {
  return createTraceGraph([...graph.nodes, node], graph.edges);
}

export function addTraceEdge(graph: TraceGraph, edge: TraceEdge): TraceGraph {
  const nodeIds = new Set(graph.nodes.map((node) => node.id));
  if (!nodeIds.has(edge.from) || !nodeIds.has(edge.to)) return graph;
  return createTraceGraph(graph.nodes, [...graph.edges, edge]);
}

export function getUpstreamTraceNodes(graph: TraceGraph, nodeId: string): TraceNode[] {
  const upstreamIds = graph.edges.filter((edge) => edge.to === nodeId).map((edge) => edge.from);
  return graph.nodes.filter((node) => upstreamIds.includes(node.id));
}

export function getDownstreamTraceNodes(graph: TraceGraph, nodeId: string): TraceNode[] {
  const downstreamIds = graph.edges.filter((edge) => edge.from === nodeId).map((edge) => edge.to);
  return graph.nodes.filter((node) => downstreamIds.includes(node.id));
}

export function buildAnswerTraceGraph(input: { answerId: string; sourceIds: string[]; planId?: string }): TraceGraph {
  const answer: TraceNode = { id: input.answerId, type: 'answer', label: 'Assistant answer' };
  const sources = input.sourceIds.map((sourceId): TraceNode => ({ id: sourceId, type: inferSourceNodeType(sourceId), label: sourceId }));
  const plan = input.planId ? [{ id: input.planId, type: 'plan' as const, label: 'Assistant plan' }] : [];
  const edges: TraceEdge[] = [
    ...sources.map((source) => ({ from: source.id, to: answer.id, relationship: 'informed_by' as const })),
    ...plan.map((planNode) => ({ from: planNode.id, to: answer.id, relationship: 'triggered' as const })),
  ];
  return createTraceGraph([answer, ...sources, ...plan], edges);
}

function inferSourceNodeType(sourceId: string): TraceNodeType {
  if (sourceId.includes('pr')) return 'pull_request';
  if (sourceId.includes('issue')) return 'issue';
  if (sourceId.includes('source')) return 'source';
  if (sourceId.includes('memory')) return 'memory';
  return 'document';
}

function dedupeNodes(nodes: TraceNode[]): TraceNode[] { return Array.from(new Map(nodes.map((node) => [node.id, node])).values()); }
function dedupeEdges(edges: TraceEdge[]): TraceEdge[] { return Array.from(new Map(edges.map((edge) => [`${edge.from}:${edge.relationship}:${edge.to}`, edge])).values()); }
