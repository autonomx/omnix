export type FlowTrigger = 'manual' | 'scheduled' | 'event' | 'condition';
export type FlowOutput = 'chat_response' | 'draft_email' | 'report' | 'artifact' | 'timeline_update';
export type FlowItem = { id: string; label: string; description: string; triggers: FlowTrigger[]; outputs: FlowOutput[]; promptPrefix: string };
export type FlowPlan = { flowId: string; prompt: string; outputs: FlowOutput[]; approvalPoints: string[] };
export type FlowRegistry = { register: (flow: FlowItem) => FlowRegistry; list: () => FlowItem[]; get: (flowId: string) => FlowItem | undefined; compile: (flowId: string, prompt: string) => FlowPlan | undefined };

export function listFlows(flows: FlowItem[]): FlowItem[] { return [...flows]; }
