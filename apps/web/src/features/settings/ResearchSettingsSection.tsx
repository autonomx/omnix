import { useEffect, useState } from 'react';
import { omnixApiClient } from '../../api/client';
import { SettingsAdvanced, SettingsField, SettingsSection, SettingsStatusRow } from './SettingsPrimitives';
import { useSettingsProfileContext } from './SettingsProfileContext';

type ResearchRuntimeStatus = {
  default_mode: string;
  provider: {
    provider: string;
    available: boolean;
    credential_required: boolean;
    credential_configured: boolean;
    coverage: string;
  };
  budgets: {
    quick_max_results: number;
    deep_max_steps: number;
    deep_max_queries: number;
    deep_max_sources: number;
    deep_max_extracts: number;
  };
  retention: {
    search_cache_ttl_seconds: number;
    extraction_cache_ttl_seconds: number;
    raw_snapshot_retention_days: number;
    source_manifest_retention_days: number;
  };
  deep_enabled: boolean;
  hermes_planner_enabled: boolean;
  diagnostics_enabled: boolean;
};

export function ResearchSettingsSection() {
  const { state, dispatch } = useSettingsProfileContext();
  const value = state.draft.assistant;
  const [runtime, setRuntime] = useState<ResearchRuntimeStatus>();
  const [statusMessage, setStatusMessage] = useState('Checking research runtime…');

  useEffect(() => {
    let active = true;
    omnixApiClient.get<ResearchRuntimeStatus>('/api/assistant/research/status').then((result) => {
      if (!active) return;
      setRuntime(result);
      setStatusMessage('Research runtime status loaded.');
    }).catch((error) => {
      if (!active) return;
      setStatusMessage(error instanceof Error ? error.message : 'Research runtime status is unavailable.');
    });
    return () => { active = false; };
  }, []);

  const numberField = (
    label: string,
    path: string,
    current: number,
    min: number,
    max: number,
    step = 1,
  ) => (
    <SettingsField label={label}>
      <input
        type="number"
        min={min}
        max={max}
        step={step}
        value={current}
        onChange={(event) => dispatch({ type: 'update', path, value: Number(event.currentTarget.value) })}
      />
    </SettingsField>
  );

  return (
    <SettingsSection
      title="Web research"
      description="Defaults apply to new Quick Search turns and new durable Deep Research jobs. API keys remain environment-owned."
      scope="module"
    >
      <div className="settings-form-grid">
        <SettingsField label="Search provider" help="Brave and Tavily require OMNIX_WEB_SEARCH_API_KEY on the server.">
          <select value={value.researchProvider} onChange={(event) => dispatch({ type: 'update', path: 'assistant.researchProvider', value: event.currentTarget.value })}>
            <option value="duckduckgo">DuckDuckGo Instant Answer · limited fallback</option>
            <option value="brave">Brave Search · general web search</option>
            <option value="tavily">Tavily · general web search</option>
          </select>
        </SettingsField>
        {numberField('Quick results', 'assistant.researchMaxResults', value.researchMaxResults, 1, 8)}
      </div>

      <div className="settings-toggle-list">
        <label><input type="checkbox" checked={value.researchDeepEnabled} onChange={(event) => dispatch({ type: 'update', path: 'assistant.researchDeepEnabled', value: event.currentTarget.checked })} /><span>Enable Deep Research for rollout</span></label>
        <label><input type="checkbox" checked={value.researchShowDiagnostics} onChange={(event) => dispatch({ type: 'update', path: 'assistant.researchShowDiagnostics', value: event.currentTarget.checked })} /><span>Show research diagnostics and source details</span></label>
        <label><input type="checkbox" checked={value.researchHermesPlannerEnabled} onChange={(event) => dispatch({ type: 'update', path: 'assistant.researchHermesPlannerEnabled', value: event.currentTarget.checked })} /><span>Prefer Hermes research planner when Hermes is enabled</span></label>
      </div>

      <SettingsAdvanced label="Budgets, cache, and retention">
        <div className="settings-form-grid">
          {numberField('Maximum steps', 'assistant.researchMaxSteps', value.researchMaxSteps, 1, 12)}
          {numberField('Maximum queries', 'assistant.researchMaxQueries', value.researchMaxQueries, 1, 10)}
          {numberField('Maximum sources', 'assistant.researchMaxSources', value.researchMaxSources, 1, 30)}
          {numberField('Maximum page extracts', 'assistant.researchMaxExtracts', value.researchMaxExtracts, 0, 20)}
          {numberField('Search cache TTL (seconds)', 'assistant.researchSearchCacheTtlSeconds', value.researchSearchCacheTtlSeconds, 1, 86400)}
          {numberField('Extraction cache TTL (seconds)', 'assistant.researchExtractionCacheTtlSeconds', value.researchExtractionCacheTtlSeconds, 1, 604800)}
          {numberField('Raw page retention (days)', 'assistant.researchRawRetentionDays', value.researchRawRetentionDays, 0, 365)}
          {numberField('Manifest retention (days)', 'assistant.researchManifestRetentionDays', value.researchManifestRetentionDays, 1, 3650)}
        </div>
      </SettingsAdvanced>

      <div className="settings-status-list" aria-label="Research runtime status">
        <SettingsStatusRow
          label="Provider"
          value={runtime ? `${runtime.provider.provider} · ${runtime.provider.available ? 'Ready' : 'Credential required'}` : 'Checking'}
          tone={runtime?.provider.available ? 'ready' : runtime ? 'warning' : 'idle'}
        />
        <SettingsStatusRow
          label="Coverage"
          value={runtime?.provider.coverage ?? 'Not reported'}
          tone="neutral"
        />
        <SettingsStatusRow
          label="Credentials"
          value={runtime ? (runtime.provider.credential_required ? (runtime.provider.credential_configured ? 'Configured' : 'Not configured') : 'Not required') : 'Checking'}
          tone={runtime?.provider.available ? 'ready' : runtime ? 'warning' : 'idle'}
        />
      </div>
      <p className="settings-inline-status" role="status">{statusMessage}</p>
    </SettingsSection>
  );
}
