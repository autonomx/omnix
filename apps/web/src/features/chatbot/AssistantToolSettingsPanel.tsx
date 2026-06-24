import { useMemo, useState } from 'react';
import {
  canExecuteToolAction,
  updateToolActionApprovalPolicy,
  updateToolActionEnabled,
  type ApprovalPolicy,
  type ToolAction,
} from '../assistant-workspace/tool-actions';
import { createDefaultAssistantToolRegistry, type AssistantTool, type ToolConfig } from '../assistant-workspace/tool-registry';

export type AssistantToolSettingsPanelProps = {
  enabledToolCount: number;
  toolExecutionRows: number;
  onShowExecutionPanel: () => void;
};

type ToolConfigState = Record<string, ToolConfig>;
type ToolActionState = Record<string, ToolAction[]>;

const approvalPolicies: Array<{ value: ApprovalPolicy; label: string }> = [
  { value: 'allow_automatic', label: 'Allow automatic' },
  { value: 'ask_sensitive', label: 'Ask for sensitive' },
  { value: 'always_ask', label: 'Always ask' },
  { value: 'disabled', label: 'Disabled' },
];

export function AssistantToolSettingsPanel({ enabledToolCount, onShowExecutionPanel, toolExecutionRows }: AssistantToolSettingsPanelProps) {
  const registry = useMemo(() => createDefaultAssistantToolRegistry(), []);
  const tools = registry.list();
  const [activeToolId, setActiveToolId] = useState(tools[0]?.id ?? '');
  const [toolConfigs, setToolConfigs] = useState<ToolConfigState>(() =>
    Object.fromEntries(tools.map((tool) => [tool.id, tool.defaultConfig])),
  );
  const [toolActions, setToolActions] = useState<ToolActionState>(() =>
    Object.fromEntries(tools.map((tool) => [tool.id, [...tool.actions]])),
  );

  const activeTool = registry.get(activeToolId) ?? tools[0];
  const activeConfig = activeTool ? toolConfigs[activeTool.id] ?? activeTool.defaultConfig : undefined;
  const activeActions = activeTool ? toolActions[activeTool.id] ?? [...activeTool.actions] : [];
  const enabledActions = activeActions.filter((action) => action.enabled).length;

  function setToolEnabled(tool: AssistantTool, enabled: boolean): void {
    setToolConfigs((current) => ({
      ...current,
      [tool.id]: {
        ...(current[tool.id] ?? tool.defaultConfig),
        enabled,
        connectionStatus: enabled ? 'connected' : 'not_configured',
      },
    }));
  }

  function setActionEnabled(tool: AssistantTool, action: ToolAction, enabled: boolean): void {
    setToolActions((current) => ({
      ...current,
      [tool.id]: (current[tool.id] ?? [...tool.actions]).map((candidate) =>
        candidate.id === action.id ? updateToolActionEnabled(candidate, enabled) : candidate,
      ),
    }));
  }

  function setActionPolicy(tool: AssistantTool, action: ToolAction, approvalPolicy: ApprovalPolicy): void {
    setToolActions((current) => ({
      ...current,
      [tool.id]: (current[tool.id] ?? [...tool.actions]).map((candidate) =>
        candidate.id === action.id ? updateToolActionApprovalPolicy(candidate, approvalPolicy) : candidate,
      ),
    }));
  }

  return (
    <section className="assistant-view-panel assistant-tool-settings-panel" aria-label="Tools view">
      <p className="eyebrow">Omnix Assistant</p>
      <h2>Tools</h2>
      <p>Configure assistant-only tool access, action approval, and connection readiness. Every action is governed before it can become an executable capability.</p>
      <div className="assistant-tool-settings-layout">
        <div className="assistant-tool-config-list" aria-label="Registered assistant tools">
          {tools.map((tool) => {
            const config = toolConfigs[tool.id] ?? tool.defaultConfig;
            const actions = toolActions[tool.id] ?? [...tool.actions];
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
