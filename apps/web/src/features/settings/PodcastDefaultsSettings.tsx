import { SettingsField, SettingsSection } from './SettingsPrimitives';
import { useSettingsProfileContext } from './SettingsProfileContext';

export function PodcastDefaultsSettings() {
  const { state, dispatch } = useSettingsProfileContext();
  const value = state.draft.podcast;
  return <SettingsSection title="Podcast" scope="module"><div className="settings-form-grid"><SettingsField label="Format"><input value={value.format} onChange={(event) => dispatch({ type: 'update', path: 'podcast.format', value: event.currentTarget.value })} /></SettingsField><SettingsField label="Duration"><input type="number" value={value.durationMinutes} onChange={(event) => dispatch({ type: 'update', path: 'podcast.durationMinutes', value: Number(event.currentTarget.value) })} /></SettingsField><SettingsField label="Tone"><input value={value.tone} onChange={(event) => dispatch({ type: 'update', path: 'podcast.tone', value: event.currentTarget.value })} /></SettingsField><SettingsField label="Language"><input value={value.language} onChange={(event) => dispatch({ type: 'update', path: 'podcast.language', value: event.currentTarget.value })} /></SettingsField></div></SettingsSection>;
}
