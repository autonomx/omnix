import type { components } from '../../api/generated/types';

type ToolRequest = components['schemas']['AssistantToolRequest'];
type ToolProposal = components['schemas']['AssistantToolProposalPayload'];
type ToolExecution = components['schemas']['HermesAssistantToolExecutePayload'];

async function post<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(path, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  if (!response.ok) throw new Error(`Assistant tool request failed: ${response.status}`);
  return response.json() as Promise<T>;
}

export async function executeToolProposal(request: ToolRequest, confirm = false): Promise<ToolExecution> {
  const proposal = await post<ToolProposal>('/api/assistant/tools/proposals', request);
  const path = `/api/assistant/tools/proposals/${encodeURIComponent(proposal.proposal_id)}`;
  if (proposal.approval_required) {
    if (!confirm) throw new Error('Assistant tool requires explicit approval.');
    await post<ToolProposal>(`${path}/approve`, {});
  }
  return post<ToolExecution>(`${path}/execute`);
}
