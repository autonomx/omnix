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

export type AssistantToolLedgerEntry = {
  execution_id: string;
  session_id?: string | null;
  tool_id: string;
  action_id: string;
  approval_source: string;
  input_summary: string;
  result_summary: string;
  state_changed: boolean;
  error?: string | null;
  created_at: string;
};

export type AssistantToolLedgerPayload = {
  entries: AssistantToolLedgerEntry[];
};

export type AssistantToolIntent = {
  detected: boolean;
  tool_id?: string | null;
  action_id?: string | null;
  confidence: number;
  preview_title: string;
  preview_summary: string;
  input: Record<string, unknown>;
};

export type AssistantCapabilityStatus = {
  tool_id: string;
  name: string;
  enabled: boolean;
  connection_status: ToolConfig['connectionStatus'];
  action_count: number;
  enabled_action_count: number;
  recent_execution_count: number;
  recent_error_count: number;
};

export type AssistantCapabilityDashboard = {
  tools: AssistantCapabilityStatus[];
  total_tools: number;
  enabled_tools: number;
  recent_execution_count: number;
  recent_error_count: number;
};

async function readJsonResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    throw new Error(`Assistant tool request failed: ${response.status}`);
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

export async function fetchAssistantToolLedger(): Promise<AssistantToolLedgerPayload> {
  return readJsonResponse<AssistantToolLedgerPayload>(await fetch('/api/assistant/tools/ledger'));
}

export async function detectAssistantToolIntent(message: string): Promise<AssistantToolIntent> {
  return readJsonResponse<AssistantToolIntent>(
    await fetch('/api/assistant/tools/intent', {
      body: JSON.stringify({ message }),
      headers: { 'Content-Type': 'application/json' },
      method: 'POST',
    }),
  );
}

export async function fetchAssistantCapabilityDashboard(): Promise<AssistantCapabilityDashboard> {
  return readJsonResponse<AssistantCapabilityDashboard>(await fetch('/api/assistant/tools/dashboard'));
}
