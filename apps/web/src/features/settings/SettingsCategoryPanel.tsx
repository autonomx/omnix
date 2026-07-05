import { SETTINGS_CATEGORIES } from './settingsRegistry';
import { SettingsSection } from './SettingsPrimitives';
import type { SettingsCategoryId } from './settingsTypes';

export function SettingsCategoryPanel({ categoryId }: { categoryId: SettingsCategoryId }) {
  const category = SETTINGS_CATEGORIES.find((entry) => entry.id === categoryId) ?? SETTINGS_CATEGORIES[0]!;
  return (
    <div className="settings-category-panel" aria-labelledby="settings-category-title">
      <div className="settings-category-title-row">
        <div>
          <p className="eyebrow">Settings category</p>
          <h2 id="settings-category-title">{category.label}</h2>
          <p>{category.description}</p>
        </div>
      </div>
      <SettingsSection title="Configuration" description="This category is ready for its roadmap implementation slice." scope="module">
        <div className="settings-planned-state">
          <strong>Control Center foundation active</strong>
          <p>Supported controls will appear here as their persistence and runtime contracts are enabled.</p>
        </div>
      </SettingsSection>
    </div>
  );
}
