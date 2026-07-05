import type { ProviderFacadePayload } from '../../api/client';
import { modelOptions, providerOptions } from './providerOptions';
import { SettingsField, SettingsSection } from './SettingsPrimitives';
import { useSettingsProfileContext } from './SettingsProfileContext';

function optionsWithCurrent(options: Array<{ id: string; label: string }>, current: string) {
  return current && !options.some((option) => option.id === current) ? [{ id: current, label: `${current} (unavailable)` }, ...options] : options;
}

export function ProviderDefaultsSection({ payload }: { payload?: ProviderFacadePayload }) {
  const { state, dispatch } = useSettingsProfileContext();
  const providers = state.draft.global.providers;
  const models = state.draft.global.models;
  const llmOptions = optionsWithCurrent(providerOptions(payload, 'chat'), providers.llm);
  const chatModels = optionsWithCurrent(modelOptions(payload, providers.llm), models.chat);
  const ttsOptions = optionsWithCurrent(providerOptions(payload, 'tts'), providers.tts);
  const sttOptions = optionsWithCurrent(providerOptions(payload, 'stt'), providers.stt);
  const imageOptions = optionsWithCurrent(providerOptions(payload, 'image'), providers.image);

  return (
    <SettingsSection title="Default providers" description="Defaults apply to new sessions and jobs. Module workspaces can override them." scope="global">
      <div className="settings-form-grid">
        <SettingsField label="Default LLM provider">
          <select value={providers.llm} onChange={(event) => dispatch({ type: 'update', path: 'global.providers.llm', value: event.currentTarget.value })}>
            {llmOptions.map((option) => <option key={option.id} value={option.id}>{option.label}</option>)}
          </select>
        </SettingsField>
        <SettingsField label="Default chat model">
          <select value={models.chat} onChange={(event) => dispatch({ type: 'update', path: 'global.models.chat', value: event.currentTarget.value })}>
            <option value="">Provider default</option>
            {chatModels.map((option) => <option key={option.id} value={option.id}>{option.label}</option>)}
          </select>
        </SettingsField>
        <SettingsField label="Default TTS provider">
          <select value={providers.tts} onChange={(event) => dispatch({ type: 'update', path: 'global.providers.tts', value: event.currentTarget.value })}>
            {ttsOptions.map((option) => <option key={option.id} value={option.id}>{option.label}</option>)}
          </select>
        </SettingsField>
        <SettingsField label="Default STT provider">
          <select value={providers.stt} onChange={(event) => dispatch({ type: 'update', path: 'global.providers.stt', value: event.currentTarget.value })}>
            {sttOptions.map((option) => <option key={option.id} value={option.id}>{option.label}</option>)}
          </select>
        </SettingsField>
        <SettingsField label="Default image provider">
          <select value={providers.image} onChange={(event) => dispatch({ type: 'update', path: 'global.providers.image', value: event.currentTarget.value })}>
            <option value="">Runtime default</option>
            {imageOptions.map((option) => <option key={option.id} value={option.id}>{option.label}</option>)}
          </select>
        </SettingsField>
      </div>
    </SettingsSection>
  );
}
