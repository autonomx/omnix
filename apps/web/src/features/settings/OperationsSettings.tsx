import { SettingsField, SettingsSection } from './SettingsPrimitives';
import { useSettingsProfileContext } from './SettingsProfileContext';

export type OperationsSettingsView = 'storage' | 'runtime';

export function OperationsSettings({ view = 'storage' }: { view?: OperationsSettingsView }) {
  const { state, dispatch } = useSettingsProfileContext();
  const storage = state.draft.storage;
  if (view === 'runtime') {
    return <div><h2>Runtime</h2><SettingsSection title="System summary" scope="status">Runtime details are loading.</SettingsSection></div>;
  }
  return <div><h2>Jobs, Assets & Storage</h2><SettingsSection title="Output defaults" scope="global"><SettingsField label="Retention days"><input type="number" min="1" max="3650" value={storage.retentionDays} onChange={(event) => dispatch({ type: 'update', path: 'storage.retentionDays', value: Number(event.currentTarget.value) })} /></SettingsField><label><input type="checkbox" checked={storage.saveOutputByDefault} onChange={(event) => dispatch({ type: 'update', path: 'storage.saveOutputByDefault', value: event.currentTarget.checked })} />Store new outputs</label></SettingsSection></div>;
}
