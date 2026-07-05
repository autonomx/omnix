import { useState } from 'react';
import { WorkspacePanel } from '../../design/primitives';
import { NarrativeSettings } from './NarrativeSettings';
import { SettingsActionHeader } from './SettingsActionHeader';
import { SettingsCategoryPanel } from './SettingsCategoryPanel';
import { SettingsCategoryRail } from './SettingsCategoryRail';
import { SettingsProfileProvider } from './SettingsProfileProvider';
import { SettingsStatusRail } from './SettingsStatusRail';
import type { SettingsCategoryId } from './settingsTypes';
import './SettingsControlCenter.css';
import './SettingsComponents.css';
import './SettingsResponsive.css';

export function SettingsControlCenter() {
  const [activeCategory, setActiveCategory] = useState<SettingsCategoryId>('ai-providers');
  const [query, setQuery] = useState('');
  const content = activeCategory.length === 19 ? <NarrativeSettings /> : <SettingsCategoryPanel categoryId={activeCategory} />;
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
