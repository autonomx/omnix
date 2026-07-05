import { AiProvidersSettings } from './AiProvidersSettings';
import { AppearanceSettings } from './AppearanceSettings';
import { SETTINGS_CATEGORIES } from './settingsRegistry';
import { SettingsSection } from './SettingsPrimitives';
import type { SettingsCategoryId } from './settingsTypes';

export function SettingsCategoryPanel({ categoryId }: { categoryId: SettingsCategoryId }) {
  if (categoryId === 'ai-providers') return <AiProvidersSettings />;
  if (categoryId === 'appearance-accessibility') return <AppearanceSettings />;
  const category = SETTINGS_CATEGORIES.find((entry) => entry.id === categoryId) ?? SETTINGS_CATEGORIES[0]!;
  return <div><h2>{category.label}</h2><p>{category.description}</p><SettingsSection title="Configuration" scope="module">Planned settings will appear here.</SettingsSection></div>;
}
