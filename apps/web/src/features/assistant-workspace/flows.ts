export type FlowItem = { id: string; label: string };
export function listFlows(flows: FlowItem[]): FlowItem[] { return [...flows]; }
