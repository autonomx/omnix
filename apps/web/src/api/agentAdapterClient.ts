import { createAgentAdapterPlaceholder, type OmnixAdapterRequest, type OmnixAdapterResult } from '../app/omnixAdapterContract';

export interface AgentAdapterStubRequest {
  input: string;
  context?: Record<string, unknown>;
}

export function readAgentAdapterStub(request: AgentAdapterStubRequest): OmnixAdapterResult {
  const adapterRequest: OmnixAdapterRequest = {
    mode: 'agent',
    input: request.input,
    context: request.context,
  };
  return createAgentAdapterPlaceholder(adapterRequest);
}
