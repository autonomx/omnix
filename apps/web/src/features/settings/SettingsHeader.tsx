export function SettingsHeader({ dirtyCount, saving, onDiscard, onSave }: {
  dirtyCount: number;
  saving?: boolean;
  onDiscard: () => void;
  onSave: () => void;
}) {
  return (
    <header className="settings-control-header">
      <div className="settings-title-block">
        <p><span>Omnix</span> / Settings</p>
        <h1>Settings Control Center</h1>
        <small>Manage providers, models, services, modules, and assistant behavior.</small>
      </div>
      <div className="settings-save-actions">
        <span>{dirtyCount ? `${dirtyCount} unsaved changes` : 'Saved'}</span>
        <button type="button" onClick={onDiscard} disabled={!dirtyCount || saving}>Discard</button>
        <button type="button" className="settings-primary-button" onClick={onSave} disabled={!dirtyCount || saving}>{saving ? 'Saving...' : 'Save changes'}</button>
      </div>
    </header>
  );
}
