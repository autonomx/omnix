export type FlowTrigger = 'manual' | 'scheduled' | 'event' | 'condition';
export type FlowOutput = 'chat_response' | 'draft_email' | 'report' | 'artifact' | 'timeline_update';
export type FlowItem = { id: string; label: string; description: string; triggers: FlowTrigger[]; outputs: FlowOutput[]; promptPrefix: string };
export type FlowPlan = { flowId: string; prompt: string; outputs: FlowOutput[]; approvalPoints: string[] };
export type FlowRegistry = { register: (flow: FlowItem) => FlowRegistry; list: () => FlowItem[]; get: (flowId: string) => FlowItem | undefined; compile: (flowId: string, prompt: string) => FlowPlan | undefined };

export function createFlowRegistry(flows: FlowItem[] = []): FlowRegistry {
  const registry = new Map<string, FlowItem>();
  for (const flow of flows) registry.set(flow.id, flow);
  return {
    register(flow) { registry.set(flow.id, flow); return this; },
    list() { return Array.from(registry.values()); },
    get(flowId) { return registry.get(flowId); },
    compile(flowId, prompt) {
      const flow = registry.get(flowId);
      if (!flow) return undefined;
      return { flowId, prompt: `${flow.promptPrefix}: ${prompt}`, outputs: flow.outputs, approvalPoints: [] };
    },
  };
}

export function listFlows(flows: FlowItem[]): FlowItem[] { return [...flows]; }
