import { SettingsSection } from './SettingsPrimitives';

export type OperationsSettingsView = 'storage' | 'runtime';

export function OperationsSettings({ view = 'storage' }: { view?: OperationsSettingsView }) {
  if (view === 'runtime') {
    return <div><h2>Runtime</h2><SettingsSection title="System summary" scope="status">Runtime details are loading.</SettingsSection></div>;
  }
  return <div><h2>Storage</h2><SettingsSection title="Output defaults" scope="global">Storage controls are loading.</SettingsSection></div>;
}
