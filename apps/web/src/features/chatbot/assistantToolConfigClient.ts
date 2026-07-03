import type { ApprovalPolicy } from '../assistant-workspace/tool-actions';
import type { ToolConfig } from '../assistant-workspace/tool-registry';

export type AssistantActionConfigRecord = {
  action_id: string;
  enabled: boolean;
  approval_policy: ApprovalPolicy;
};

export type AssistantToolConfigRecord = {
  tool_id: string;
  enabled: boolean;
  connection_status: ToolConfig['connectionStatus'];
  approval_policy?: ApprovalPolicy | null;
  actions: AssistantActionConfigRecord[];
};

export type AssistantToolsConfigPayload = {
  tools: AssistantToolConfigRecord[];
};

async function readJsonResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    throw new Error(`Assistant tool config request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export async function fetchAssistantToolsConfig(): Promise<AssistantToolsConfigPayload> {
  return readJsonResponse<AssistantToolsConfigPayload>(await fetch('/api/assistant/tools/config'));
}

export async function saveAssistantToolsConfig(payload: AssistantToolsConfigPayload): Promise<AssistantToolsConfigPayload> {
  return readJsonResponse<AssistantToolsConfigPayload>(
    await fetch('/api/assistant/tools/config', {
      body: JSON.stringify(payload),
      headers: { 'Content-Type': 'application/json' },
      method: 'POST',
    }),
  );
}
