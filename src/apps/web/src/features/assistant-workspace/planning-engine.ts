import type { AssistantCapability } from './derived-capabilities';

export type IntentPlan = { intent: string; goal: string; confidence: number };
export type RetrievalPlan = { sourceIds: string[]; needsFreshness: boolean; needsVerification: boolean };
export type ExecutionPlan = { actionIds: string[]; unavailableActionIds: string[]; requiresApproval: boolean };
export type ResponseOutput = 'chat_response' | 'draft_email' | 'timeline_update' | 'artifact' | 'workflow_report';
export type ResponsePlan = { outputs: ResponseOutput[]; tone: 'brief' | 'normal' | 'detailed'; includeCitations: boolean };

export type AssistantPlan = {
  intent: IntentPlan;
  retrieval: RetrievalPlan;
  execution: ExecutionPlan;
  response: ResponsePlan;
};

export type PlanningInput = {
  prompt: string;
  capabilities: AssistantCapability[];
};

export function createIntentPlan(prompt: string): IntentPlan {
  const normalized = prompt.toLowerCase();
  if (normalized.includes('review') && normalized.includes('pr')) {
    return { intent: 'review_pull_request', goal: 'Review a pull request and summarize findings.', confidence: 0.85 };
  }
  if (normalized.includes('email') || normalized.includes('draft')) {
    return { intent: 'compose_communication', goal: 'Prepare a communication artifact.', confidence: 0.8 };
  }
  if (normalized.includes('latest') || normalized.includes('current') || normalized.includes('search')) {
    return { intent: 'answer_with_fresh_context', goal: 'Answer with current and verifiable context.', confidence: 0.8 };
  }
  return { intent: 'general_assistant_response', goal: 'Answer the user in chat.', confidence: 0.6 };
}

export function createRetrievalPlan(prompt: string): RetrievalPlan {
  const normalized = prompt.toLowerCase();
  const sourceIds = ['memory', 'workspace_documents'];
  const needsFreshness = normalized.includes('latest') || normalized.includes('current') || normalized.includes('today') || normalized.includes('search');
  const needsVerification = normalized.includes('verify') || normalized.includes('source') || normalized.includes('citation');
  if (normalized.includes('pr') || normalized.includes('github')) sourceIds.push('github_source');
  if (needsFreshness || needsVerification) sourceIds.push('web_research');
  return { sourceIds: Array.from(new Set(sourceIds)), needsFreshness, needsVerification };
}

export function createExecutionPlan(prompt: string, capabilities: AssistantCapability[]): ExecutionPlan {
  const normalized = prompt.toLowerCase();
  const requested = new Set<string>();
  if (normalized.includes('email')) requested.add('gmail.create_draft');
  if (normalized.includes('send email')) requested.add('gmail.send_email');
  if (normalized.includes('pr')) requested.add('github.read_pr');
  if (normalized.includes('create pr')) requested.add('github.create_pr');
  if (normalized.includes('merge pr')) requested.add('github.merge_pr');
  const available = new Set(capabilities.filter((capability) => capability.available).map((capability) => capability.id));
  const actionIds = Array.from(requested).filter((id) => available.has(id));
  const unavailableActionIds = Array.from(requested).filter((id) => !available.has(id));
  const requiresApproval = actionIds.some((id) => capabilities.find((capability) => capability.id === id)?.riskLevel === 'high');
  return { actionIds, unavailableActionIds, requiresApproval };
}

export function createResponsePlan(prompt: string, retrieval: RetrievalPlan, execution: ExecutionPlan): ResponsePlan {
  const normalized = prompt.toLowerCase();
  const outputs: ResponseOutput[] = ['chat_response'];
  if (normalized.includes('email') || normalized.includes('draft')) outputs.push('draft_email');
  if (normalized.includes('report')) outputs.push('workflow_report');
  if (normalized.includes('artifact')) outputs.push('artifact');
  return { outputs: Array.from(new Set(outputs)), tone: execution.actionIds.length ? 'detailed' : 'normal', includeCitations: retrieval.needsFreshness || retrieval.needsVerification };
}

export function createAssistantPlan(input: PlanningInput): AssistantPlan {
  const intent = createIntentPlan(input.prompt);
  const retrieval = createRetrievalPlan(input.prompt);
  const execution = createExecutionPlan(input.prompt, input.capabilities);
  const response = createResponsePlan(input.prompt, retrieval, execution);
  return { intent, retrieval, execution, response };
}
