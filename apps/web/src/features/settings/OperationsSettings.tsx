export type OperationsSettingsView = 'storage' | 'runtime';

export function OperationsSettings({ view = 'storage' }: { view?: OperationsSettingsView }) {
  return <div>{view === 'runtime' ? 'Runtime summary' : 'Storage defaults'}</div>;
}
