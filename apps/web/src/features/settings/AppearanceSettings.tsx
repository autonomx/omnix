import { useEffect } from 'react';
import { applyAppearanceSettings } from './appearanceEffects';
import { SettingsField, SettingsSection } from './SettingsPrimitives';
import { useSettingsProfileContext } from './SettingsProfileContext';

export function AppearanceSettings() {
  const { state, dispatch } = useSettingsProfileContext();
  const value = state.draft.appearance;
  useEffect(() => applyAppearanceSettings(value), [value]);
  return (
    <div className="settings-category-panel">
      <div className="settings-category-title-row"><p className="eyebrow">Settings category</p><h2>Appearance & Accessibility</h2><p>Control theme, density, motion, and captions.</p></div>
      <SettingsSection title="Appearance" scope="local">
        <div className="settings-form-grid">
          <SettingsField label="Appearance"><select value={value.mode} onChange={(event) => dispatch({ type: 'update', path: 'appearance.mode', value: event.currentTarget.value })}><option value="system">System</option><option value="light">Light</option><option value="dark">Dark</option></select></SettingsField>
          <SettingsField label="Density"><select value={value.density} onChange={(event) => dispatch({ type: 'update', path: 'appearance.density', value: event.currentTarget.value })}><option value="comfortable">Comfortable</option><option value="compact">Compact</option></select></SettingsField>
        </div>
      </SettingsSection>
      <SettingsSection title="Accessibility" scope="local"><div className="settings-toggle-list"><label><input type="checkbox" checked={value.reduceMotion} onChange={(event) => dispatch({ type: 'update', path: 'appearance.reduceMotion', value: event.currentTarget.checked })} /><span>Reduce motion</span></label><label><input type="checkbox" checked={value.liveCaptions} onChange={(event) => dispatch({ type: 'update', path: 'appearance.liveCaptions', value: event.currentTarget.checked })} /><span>Live captions</span></label></div></SettingsSection>
    </div>
  );
}
