import type { components } from '../../api/generated/types';
import { api, unwrap } from '../../api/http';

type ToolRequest = components['schemas']['AssistantToolRequest-Input'];
type ToolExecution = components['schemas']['HermesAssistantToolExecutePayload'];

export async function executeToolProposal(request: ToolRequest, confirm = false): Promise<ToolExecution> {
  const proposal = await unwrap(api.POST('/api/assistant/tools/proposals', { body: request }));
  const path = { proposal_id: proposal.proposal_id };
  if (proposal.approval_required) {
    if (!confirm) throw new Error('Assistant tool requires explicit approval.');
    await unwrap(api.POST('/api/assistant/tools/proposals/{proposal_id}/approve', { params: { path }, body: {} }));
  }
  return unwrap(api.POST('/api/assistant/tools/proposals/{proposal_id}/execute', { params: { path } }));
}
