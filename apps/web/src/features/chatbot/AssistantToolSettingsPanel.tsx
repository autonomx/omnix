import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  canExecuteToolAction,
  type ApprovalPolicy,
  type ToolAction,
} from '../assistant-workspace/tool-actions';
import { createDefaultAssistantToolRegistry, type AssistantTool, type ToolConfig } from '../assistant-workspace/tool-registry';
import {
  fetchAssistantToolsConfig,
  saveAssistantToolsConfig,
  type AssistantToolsConfigPayload,
} from './assistantToolConfigClient';

export type AssistantToolSettingsPanelProps = {
  enabledToolCount: number;
  toolExecutionRows: number;
  onShowExecutionPanel: () => void;
};

const assistantToolConfigQueryKey = ['assistant-tools', 'config'] as const;

const approvalPolicies: Array<{ value: ApprovalPolicy; label: string }> = [
  { value: 'allow_automatic', label: 'Allow automatic' },
  { value: 'ask_sensitive', label: 'Ask for sensitive' },
  { value: 'always_ask', label: 'Always ask' },
  { value: 'disabled', label: 'Disabled' },
];

export function AssistantToolSettingsPanel({ enabledToolCount, onShowExecutionPanel, toolExecutionRows }: AssistantToolSettingsPanelProps) {
  const registry = useMemo(() => createDefaultAssistantToolRegistry(), []);
  const tools = useMemo(() => registry.list(), [registry]);
  const queryClient = useQueryClient();
  const [activeToolId, setActiveToolId] = useState(tools[0]?.id ?? '');

  const configQuery = useQuery({
    queryKey: assistantToolConfigQueryKey,
    queryFn: fetchAssistantToolsConfig,
  });

  const saveMutation = useMutation({
    mutationFn: saveAssistantToolsConfig,
    onSuccess(saved) {
      queryClient.setQueryData(assistantToolConfigQueryKey, saved);
    },
  });

  const configPayload = configQuery.data ?? createFallbackConfigPayload(tools);
  const activeTool = registry.get(activeToolId) ?? tools[0];
  const activeToolRecord = activeTool ? getToolRecord(configPayload, activeTool) : undefined;
  const activeConfig = activeTool && activeToolRecord ? toToolConfig(activeToolRecord) : undefined;
  const activeActions = activeTool && activeToolRecord ? mergeActionConfig(activeTool, activeToolRecord) : [];
  const enabledActions = activeActions.filter((action) => action.enabled).length;

  function persistConfig(updater: (payload: AssistantToolsConfigPayload) => AssistantToolsConfigPayload): void {
    const basePayload = configQuery.data ?? createFallbackConfigPayload(tools);
    const nextPayload = updater(basePayload);
    queryClient.setQueryData(assistantToolConfigQueryKey, nextPayload);
    saveMutation.mutate(nextPayload);
  }

  function setToolEnabled(tool: AssistantTool, enabled: boolean): void {
    persistConfig((payload) => updateToolRecord(payload, tool.id, (record) => ({
      ...record,
      enabled,
      connection_status: enabled ? 'connected' : 'not_configured',
    })));
  }

  function setActionEnabled(tool: AssistantTool, action: ToolAction, enabled: boolean): void {
    persistConfig((payload) => updateActionRecord(payload, tool.id, action.id, (record) => ({ ...record, enabled })));
  }

  function setActionPolicy(tool: AssistantTool, action: ToolAction, approvalPolicy: ApprovalPolicy): void {
    persistConfig((payload) => updateActionRecord(payload, tool.id, action.id, (record) => ({ ...record, approval_policy: approvalPolicy })));
  }

  return (
    <section className="assistant-view-panel assistant-tool-settings-panel" aria-label="Tools view">
      <p className="eyebrow">Omnix Assistant</p>
      <h2>Tools</h2>
      <p>Configure assistant-only tool access, action approval, and connection readiness. Every action is governed before it can become an executable capability.</p>
      {configQuery.isError ? <p className="assistant-view-note">Tool configuration could not be loaded. Safe local defaults are shown until the backend is reachable.</p> : null}
      <div className="assistant-tool-settings-layout">
        <div className="assistant-tool-config-list" aria-label="Registered assistant tools">
          {tools.map((tool) => {
            const record = getToolRecord(configPayload, tool);
            const config = toToolConfig(record);
            const actions = mergeActionConfig(tool, record);
            return (
              <ToolConfigCard
                actionCount={actions.length}
                active={tool.id === activeTool?.id}
                config={config}
                enabledActionCount={actions.filter((action) => action.enabled).length}
                key={tool.id}
                onConfigure={() => setActiveToolId(tool.id)}
                onToggle={(enabled) => setToolEnabled(tool, enabled)}
                tool={tool}
              />
            );
          })}
        </div>
        {activeTool && activeConfig ? (
          <div className="assistant-tool-config-drawer" aria-label={`${activeTool.metadata.name} configuration`}>
            <header>
              <div>
                <p className="eyebrow">Configuration</p>
                <h3>{activeTool.metadata.name}</h3>
              </div>
              <ToolStatusBadge config={activeConfig} />
            </header>
            <p>{activeTool.metadata.description}</p>
            <dl className="assistant-settings-list">
              <div><dt>Provider</dt><dd>{activeTool.metadata.provider ?? 'Omnix'}</dd></div>
              <div><dt>Category</dt><dd>{activeTool.category.replace('_', ' ')}</dd></div>
              <div><dt>Connection</dt><dd>{activeConfig.connectionStatus.replace('_', ' ')}</dd></div>
              <div><dt>Enabled actions</dt><dd>{enabledActions}/{activeActions.length}</dd></div>
              <div><dt>Persistence</dt><dd>{saveMutation.isPending ? 'Saving' : configQuery.isLoading ? 'Loading' : 'Backend saved'}</dd></div>
            </dl>
            <div className="assistant-tool-config-actions">
              <button type="button" onClick={() => setToolEnabled(activeTool, !activeConfig.enabled)}>{activeConfig.enabled ? 'Disable tool' : 'Enable tool'}</button>
              <button type="button" onClick={onShowExecutionPanel}>Show execution panel</button>
              <button type="button" onClick={() => void activeTool.testConnection(activeConfig)}>Test connection</button>
            </div>
            <div className="assistant-tool-action-list" aria-label={`${activeTool.metadata.name} actions`}>
              {activeActions.map((action) => {
                const gate = canExecuteToolAction(action);
                return (
                  <article className="assistant-tool-action-row" key={action.id}>
                    <div>
                      <h4>{action.label}</h4>
                      <p>{action.description}</p>
                      <small>{action.id} · {action.category} · {action.riskLevel} risk{action.isDestructive ? ' · destructive' : ''}{action.requiresConfirmation ? ' · confirmation required' : ''}</small>
                    </div>
                    <label className="assistant-tool-toggle">
                      <span>{action.enabled ? 'Enabled' : 'Disabled'}</span>
                      <input checked={action.enabled} onChange={(event) => setActionEnabled(activeTool, action, event.currentTarget.checked)} type="checkbox" />
                    </label>
                    <label className="assistant-tool-policy-select">
                      <span>Approval</span>
                      <select value={action.approvalPolicy} onChange={(event) => setActionPolicy(activeTool, action, event.currentTarget.value as ApprovalPolicy)}>
                        {approvalPolicies.map((policy) => <option key={policy.value} value={policy.value}>{policy.label}</option>)}
                      </select>
                    </label>
                    <strong>{gate.allowed ? gate.approvalRequired ? 'Approval required' : 'Ready' : 'Blocked'}</strong>
                  </article>
                );
              })}
            </div>
          </div>
        ) : null}
      </div>
      <p className="assistant-view-note">{enabledToolCount} tools active · {toolExecutionRows} replayed execution rows</p>
    </section>
  );
}

function createFallbackConfigPayload(tools: AssistantTool[]): AssistantToolsConfigPayload {
  return {
    tools: tools.map((tool) => ({
      actions: tool.actions.map((action) => ({
        action_id: action.id,
        enabled: action.enabled,
        approval_policy: action.approvalPolicy,
      })),
      connection_status: tool.defaultConfig.connectionStatus,
      enabled: tool.defaultConfig.enabled,
      tool_id: tool.id,
    })),
  };
}

function getToolRecord(payload: AssistantToolsConfigPayload, tool: AssistantTool) {
  return payload.tools.find((record) => record.tool_id === tool.id) ?? createFallbackConfigPayload([tool]).tools[0];
}

function toToolConfig(record: ReturnType<typeof getToolRecord>): ToolConfig {
  return {
    enabled: record.enabled,
    connectionStatus: record.connection_status,
  };
}

function mergeActionConfig(tool: AssistantTool, record: ReturnType<typeof getToolRecord>): ToolAction[] {
  const actionConfig = new Map(record.actions.map((action) => [action.action_id, action]));
  return tool.actions.map((action) => {
    const config = actionConfig.get(action.id);
    return config ? { ...action, enabled: config.enabled, approvalPolicy: config.approval_policy } : action;
  });
}

function updateToolRecord(
  payload: AssistantToolsConfigPayload,
  toolId: string,
  updater: (record: AssistantToolsConfigPayload['tools'][number]) => AssistantToolsConfigPayload['tools'][number],
): AssistantToolsConfigPayload {
  return {
    tools: payload.tools.map((record) => (record.tool_id === toolId ? updater(record) : record)),
  };
}

function updateActionRecord(
  payload: AssistantToolsConfigPayload,
  toolId: string,
  actionId: string,
  updater: (record: AssistantToolsConfigPayload['tools'][number]['actions'][number]) => AssistantToolsConfigPayload['tools'][number]['actions'][number],
): AssistantToolsConfigPayload {
  return updateToolRecord(payload, toolId, (toolRecord) => ({
    ...toolRecord,
    actions: toolRecord.actions.map((action) => (action.action_id === actionId ? updater(action) : action)),
  }));
}

function ToolConfigCard({ actionCount, active, config, enabledActionCount, onConfigure, onToggle, tool }: { actionCount: number; active: boolean; config: ToolConfig; enabledActionCount: number; onConfigure: () => void; onToggle: (enabled: boolean) => void; tool: AssistantTool }) {
  return (
    <article className={active ? 'active' : undefined}>
      <div>
        <h3>{tool.metadata.name}</h3>
        <p>{tool.metadata.description}</p>
        <small>{enabledActionCount}/{actionCount} actions enabled</small>
      </div>
      <ToolStatusBadge config={config} />
      <label className="assistant-tool-toggle">
        <span>{config.enabled ? 'Enabled' : 'Disabled'}</span>
        <input checked={config.enabled} onChange={(event) => onToggle(event.currentTarget.checked)} type="checkbox" />
      </label>
      <button type="button" onClick={onConfigure}>Configure</button>
    </article>
  );
}

function ToolStatusBadge({ config }: { config: ToolConfig }) {
  const label = !config.enabled ? 'Disabled' : config.connectionStatus === 'connected' ? 'Enabled' : config.connectionStatus === 'error' ? 'Error' : 'Needs setup';
  return <strong>{label}</strong>;
}
