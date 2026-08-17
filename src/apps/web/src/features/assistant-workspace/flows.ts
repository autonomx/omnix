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

export const DEFAULT_ASSISTANT_FLOWS: FlowItem[] = [
  { id: 'pr_review', label: 'PR Review', description: 'Review a pull request and summarize findings.', triggers: ['manual'], outputs: ['chat_response', 'report'], promptPrefix: 'Review pull request' },
  { id: 'weekly_project_report', label: 'Weekly Project Report', description: 'Summarize project progress and risks.', triggers: ['manual', 'scheduled'], outputs: ['report'], promptPrefix: 'Create weekly project report' },
  { id: 'release_readiness', label: 'Release Readiness Check', description: 'Check readiness signals before release.', triggers: ['manual'], outputs: ['report', 'timeline_update'], promptPrefix: 'Check release readiness' },
  { id: 'sprint_summary', label: 'Sprint Summary', description: 'Summarize sprint updates and blockers.', triggers: ['manual', 'scheduled'], outputs: ['report'], promptPrefix: 'Create sprint summary' },
  { id: 'bug_triage', label: 'Bug Triage', description: 'Classify bugs and plan next actions.', triggers: ['manual', 'event'], outputs: ['chat_response', 'timeline_update'], promptPrefix: 'Triage bug' },
  { id: 'audit_review', label: 'Audit Review', description: 'Review content for sensitive data risks.', triggers: ['manual'], outputs: ['report'], promptPrefix: 'Audit sensitive data' },
  { id: 'regression_analysis', label: 'Regression Analysis', description: 'Analyze regression signals and impacted areas.', triggers: ['manual'], outputs: ['report'], promptPrefix: 'Analyze regression' },
];

export function createDefaultFlowRegistry(): FlowRegistry { return createFlowRegistry(DEFAULT_ASSISTANT_FLOWS); }
export function listFlows(flows: FlowItem[]): FlowItem[] { return [...flows]; }
