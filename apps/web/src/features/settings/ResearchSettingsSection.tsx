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
  release: {
    master_enabled: boolean;
    quick_enabled: boolean;
    quick_percentage: number;
    deep_local_enabled: boolean;
    deep_local_percentage: number;
    hermes_enabled: boolean;
    hermes_percentage: number;
    availability: {
      disabled: boolean;
      quick: boolean;
      deep: boolean;
      hermes_planner: boolean;
    };
  };
  compatibility: {
    aliases_enabled: boolean;
    sunset: string | null;
    total_legacy_requests: number;
    alias_counts: Record<string, number>;
    canonical_field: string;
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
      description="Defaults apply to new Quick Search turns and new durable Deep Research jobs. API keys and release percentages remain environment-owned."
      scope="module"
    >
      <div className="settings-form-grid">
        <SettingsField label="Search provider" help="Brave and Tavily require OMNIX_WEB_SEARCH_API_KEY on the server. Playwright uses a local browser fallback.">
          <select value={value.researchProvider} onChange={(event) => dispatch({ type: 'update', path: 'assistant.researchProvider', value: event.currentTarget.value })}>
            <option value="duckduckgo">DuckDuckGo Instant Answer · limited fallback</option>
            <option value="brave">Brave Search · general web search</option>
            <option value="tavily">Tavily · general web search</option>
            <option value="playwright">Playwright browser search - keyless fallback</option>
          </select>
        </SettingsField>
        {numberField('Quick results', 'assistant.researchMaxResults', value.researchMaxResults, 1, 8)}
      </div>

      <div className="settings-toggle-list">
        <label><input type="checkbox" checked={value.researchDeepEnabled} onChange={(event) => dispatch({ type: 'update', path: 'assistant.researchDeepEnabled', value: event.currentTarget.checked })} /><span>Enable Deep Research when released for this session</span></label>
        <label><input type="checkbox" checked={value.researchShowDiagnostics} onChange={(event) => dispatch({ type: 'update', path: 'assistant.researchShowDiagnostics', value: event.currentTarget.checked })} /><span>Show research diagnostics and source details</span></label>
        <label><input type="checkbox" checked={value.researchHermesPlannerEnabled} onChange={(event) => dispatch({ type: 'update', path: 'assistant.researchHermesPlannerEnabled', value: event.currentTarget.checked })} /><span>Prefer Hermes only when its separate release gate is active</span></label>
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
        <SettingsStatusRow label="Coverage" value={runtime?.provider.coverage ?? 'Not reported'} tone="neutral" />
        <SettingsStatusRow
          label="Credentials"
          value={runtime ? (runtime.provider.credential_required ? (runtime.provider.credential_configured ? 'Configured' : 'Not configured') : 'Not required') : 'Checking'}
          tone={runtime?.provider.available ? 'ready' : runtime ? 'warning' : 'idle'}
        />
        <SettingsStatusRow
          label="Master release"
          value={runtime ? (runtime.release.master_enabled ? 'Enabled' : 'Rollback active') : 'Checking'}
          tone={runtime?.release.master_enabled ? 'ready' : runtime ? 'warning' : 'idle'}
        />
        <SettingsStatusRow
          label="Quick Search release"
          value={runtime ? `${runtime.release.availability.quick ? 'Available' : 'Unavailable'} · ${runtime.release.quick_percentage}% cohort` : 'Checking'}
          tone={runtime?.release.availability.quick ? 'ready' : runtime ? 'warning' : 'idle'}
        />
        <SettingsStatusRow
          label="Deep Research release"
          value={runtime ? `${runtime.release.availability.deep ? 'Available' : 'Unavailable'} · ${runtime.release.deep_local_percentage}% cohort` : 'Checking'}
          tone={runtime?.release.availability.deep ? 'ready' : 'idle'}
        />
        <SettingsStatusRow
          label="Hermes planner release"
          value={runtime ? `${runtime.release.availability.hermes_planner ? 'Available' : 'Not released'} · ${runtime.release.hermes_percentage}% cohort` : 'Checking'}
          tone={runtime?.release.availability.hermes_planner ? 'ready' : 'idle'}
        />
        <SettingsStatusRow
          label="Legacy request aliases"
          value={runtime ? (runtime.compatibility.aliases_enabled ? `Temporary · sunset ${runtime.compatibility.sunset ?? 'not scheduled'}` : 'Disabled') : 'Checking'}
          tone={runtime?.compatibility.aliases_enabled ? 'warning' : runtime ? 'ready' : 'idle'}
        />
        <SettingsStatusRow
          label="Legacy alias requests"
          value={runtime ? `${runtime.compatibility.total_legacy_requests} observed · canonical ${runtime.compatibility.canonical_field}` : 'Checking'}
          tone={runtime?.compatibility.total_legacy_requests ? 'warning' : 'neutral'}
        />
      </div>
      <p className="settings-inline-status" role="status">{statusMessage}</p>
    </SettingsSection>
  );
}
