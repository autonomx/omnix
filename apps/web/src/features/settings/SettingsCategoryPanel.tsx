import { AiProvidersSettings } from './AiProvidersSettings';
import { SETTINGS_CATEGORIES } from './settingsRegistry';
import { SettingsSection } from './SettingsPrimitives';
import type { SettingsCategoryId } from './settingsTypes';

export function SettingsCategoryPanel({ categoryId }: { categoryId: SettingsCategoryId }) {
  if (categoryId === 'ai-providers') return <AiProvidersSettings />;
  const category = SETTINGS_CATEGORIES.find((entry) => entry.id === categoryId) ?? SETTINGS_CATEGORIES[0]!;
  return <div className="settings-category-panel"><h2>{category.label}</h2><p>{category.description}</p><SettingsSection title="Configuration" scope="module"><div className="settings-planned-state">Planned settings will appear here.</div></SettingsSection></div>;
}
