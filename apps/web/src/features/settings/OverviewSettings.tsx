import { SettingsSection, SettingsStatusRow } from './SettingsPrimitives';
import { useSettingsProfileContext } from './SettingsProfileContext';

export function OverviewSettings() {
  const { state, loading, loadError } = useSettingsProfileContext();
  const providers = state.draft.global.providers;
  return (
    <div className="settings-category-panel">
      <div className="settings-category-title-row"><p className="eyebrow">Settings category</p><h2>Overview</h2><p>Current defaults and profile readiness.</p></div>
      <SettingsSection title="Configuration profile" scope="global">
        <div className="settings-metric-grid">
          <div><strong>{state.dirtyPaths.length}</strong><span>Unsaved changes</span></div>
          <div><strong>{state.draft.schemaVersion}</strong><span>Schema version</span></div>
          <div><strong>{loading ? 'Loading' : 'Ready'}</strong><span>Profile state</span></div>
          <div><strong>{state.draft.storage.retentionDays}</strong><span>Retention days</span></div>
        </div>
        {loadError ? <p role="alert" className="settings-inline-status">{loadError}</p> : null}
      </SettingsSection>
      <SettingsSection title="Default services" scope="global">
        <SettingsStatusRow label="Language model" value={providers.llm || 'Runtime default'} tone="neutral" />
        <SettingsStatusRow label="Speech synthesis" value={providers.tts || 'Runtime default'} tone="neutral" />
        <SettingsStatusRow label="Speech input" value={providers.stt || 'Runtime default'} tone="neutral" />
        <SettingsStatusRow label="Image generation" value={providers.image || 'Runtime default'} tone="neutral" />
      </SettingsSection>
    </div>
  );
}
