import { useState } from 'react';
import { WorkspacePanel } from '../../design/primitives';
import { ImageSpeechSettings } from './ImageSpeechSettings';
import { NarrativeSettings } from './NarrativeSettings';
import { OperationsSettings } from './OperationsSettings';
import { RpgDefaultsSettings } from './RpgDefaultsSettings';
import { ServicesSettings } from './ServicesSettings';
import { SettingsActionHeader } from './SettingsActionHeader';
import { SettingsCategoryPanel } from './SettingsCategoryPanel';
import { SettingsCategoryRail } from './SettingsCategoryRail';
import { SettingsProfileProvider } from './SettingsProfileProvider';
import { SETTINGS_CATEGORIES } from './settingsRegistry';
import { SettingsStatusRail } from './SettingsStatusRail';
import type { SettingsCategoryId } from './settingsTypes';
import './SettingsControlCenter.css';
import './SettingsComponents.css';
import './SettingsResponsive.css';

export function SettingsControlCenter() {
  const [activeCategory, setActiveCategory] = useState<SettingsCategoryId>('ai-providers');
  const [query, setQuery] = useState('');
  const categoryIndex = SETTINGS_CATEGORIES.findIndex((item) => item.id === activeCategory);
  const content = categoryIndex === 6 ? <NarrativeSettings /> : categoryIndex === 7 ? <RpgDefaultsSettings /> : categoryIndex === 8 ? <ImageSpeechSettings /> : categoryIndex === 9 ? <ServicesSettings /> : categoryIndex === 10 ? <OperationsSettings /> : categoryIndex === 11 ? <OperationsSettings view="runtime" /> : <SettingsCategoryPanel categoryId={activeCategory} />;
  return (
    <SettingsProfileProvider>
      <WorkspacePanel className="settings-control-panel">
        <div className="settings-control-center">
          <SettingsCategoryRail activeCategory={activeCategory} query={query} onQueryChange={setQuery} onSelect={setActiveCategory} />
          <div className="settings-control-content"><SettingsActionHeader /><main className="settings-main-column">{content}</main></div>
          <SettingsStatusRail />
        </div>
      </WorkspacePanel>
    </SettingsProfileProvider>
  );
}
