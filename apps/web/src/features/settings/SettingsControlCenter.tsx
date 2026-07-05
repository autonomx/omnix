import { useState } from 'react';
import { WorkspacePanel } from '../../design/primitives';
import { SettingsCategoryPanel } from './SettingsCategoryPanel';
import { SettingsCategoryRail } from './SettingsCategoryRail';
import { SettingsHeader } from './SettingsHeader';
import { SettingsStatusRail } from './SettingsStatusRail';
import type { SettingsCategoryId } from './settingsTypes';
import './SettingsControlCenter.css';
import './SettingsComponents.css';
import './SettingsResponsive.css';

export function SettingsControlCenter() {
  const [activeCategory, setActiveCategory] = useState<SettingsCategoryId>('ai-providers');
  const [query, setQuery] = useState('');

  return (
    <WorkspacePanel className="settings-control-panel">
      <div className="settings-control-center">
        <SettingsCategoryRail activeCategory={activeCategory} query={query} onQueryChange={setQuery} onSelect={setActiveCategory} />
        <div className="settings-control-content">
          <SettingsHeader dirtyCount={0} onDiscard={() => undefined} onSave={() => undefined} />
          <main className="settings-main-column">
            <SettingsCategoryPanel categoryId={activeCategory} />
          </main>
        </div>
        <SettingsStatusRail />
      </div>
    </WorkspacePanel>
  );
}
