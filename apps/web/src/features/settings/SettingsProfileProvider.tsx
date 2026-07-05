import { useReducer, type ReactNode } from 'react';
import { DEFAULT_SETTINGS_DOCUMENT } from './settingsDefaults';
import { createSettingsDraftState, settingsDraftReducer } from './settingsDraft';
import { SettingsProfileContext } from './SettingsProfileContext';

export function SettingsProfileProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(settingsDraftReducer, DEFAULT_SETTINGS_DOCUMENT, createSettingsDraftState);
  return <SettingsProfileContext.Provider value={{ state, dispatch, loading: false, loadError: '' }}>{children}</SettingsProfileContext.Provider>;
}
