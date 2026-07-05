import { useEffect, useRef, useState } from 'react';
import { WorkspacePanel } from '../../design/primitives';
import { CatalogPanel } from './CatalogPanel';
import { ImageSpeechSettings } from './ImageSpeechSettings';
import { ModelSettings } from './ModelSettings';
import { NarrativeSettings } from './NarrativeSettings';
import { OperationsSettings } from './OperationsSettings';
import { OverviewSettings } from './OverviewSettings';
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
  const mainRef = useRef<HTMLElement | null>(null);
  const initialCategory = useRef(true);
  const categoryIndex = SETTINGS_CATEGORIES.findIndex((item) => item.id === activeCategory);
  const category = SETTINGS_CATEGORIES[categoryIndex] ?? SETTINGS_CATEGORIES[0]!;
  const content = categoryIndex === 0 ? <OverviewSettings /> : categoryIndex === 3 ? <><ModelSettings /><CatalogPanel /></> : categoryIndex === 6 ? <NarrativeSettings /> : categoryIndex === 7 ? <RpgDefaultsSettings /> : categoryIndex === 8 ? <ImageSpeechSettings /> : categoryIndex === 9 ? <ServicesSettings /> : categoryIndex === 10 ? <OperationsSettings /> : categoryIndex === 11 ? <OperationsSettings view="runtime" /> : <SettingsCategoryPanel categoryId={activeCategory} />;
  useEffect(() => {
    if (initialCategory.current) {
      initialCategory.current = false;
      return;
    }
    mainRef.current?.focus();
  }, [activeCategory]);
  return (
    <SettingsProfileProvider>
      <WorkspacePanel className="settings-control-panel">
        <a className="settings-skip-link" href="#settings-main">Skip to settings content</a>
        <div className="settings-control-center">
          <SettingsCategoryRail activeCategory={activeCategory} query={query} onQueryChange={setQuery} onSelect={setActiveCategory} />
          <div className="settings-control-content"><SettingsActionHeader /><main id="settings-main" ref={mainRef} tabIndex={-1} aria-label={`${category.label} settings`} className="settings-main-column">{content}</main></div>
          <SettingsStatusRail />
        </div>
      </WorkspacePanel>
    </SettingsProfileProvider>
  );
}
