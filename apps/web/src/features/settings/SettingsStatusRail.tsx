import { SettingsStatusRow } from './SettingsPrimitives';

export function SettingsStatusRail() {
  return (
    <aside className="settings-status-rail" aria-label="System status">
      <section className="settings-status-card">
        <h3>System status</h3>
        <SettingsStatusRow label="Gateway" value="Checking" tone="idle" />
        <SettingsStatusRow label="Language model" value="Checking" tone="idle" />
        <SettingsStatusRow label="Speech services" value="Checking" tone="idle" />
        <SettingsStatusRow label="Image worker" value="Checking" tone="idle" />
      </section>
      <section className="settings-status-card">
        <h3>Runtime resources</h3>
        <p>Status details appear when connected.</p>
      </section>
      <button className="settings-run-tests" type="button" disabled>Run all tests</button>
    </aside>
  );
}
