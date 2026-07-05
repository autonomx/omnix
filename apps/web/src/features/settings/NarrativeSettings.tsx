import { SettingsField, SettingsSection } from './SettingsPrimitives';
import { useSettingsProfileContext } from './SettingsProfileContext';

export function NarrativeSettings() {
  const { state, dispatch } = useSettingsProfileContext();
  return <SettingsSection title="Narrative defaults" scope="module"><SettingsField label="Tone"><input value={state.draft.storyteller.tone} onChange={(event) => dispatch({ type: 'update', path: 'storyteller.tone', value: event.currentTarget.value })} /></SettingsField></SettingsSection>;
}
