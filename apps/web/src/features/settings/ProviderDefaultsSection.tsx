import type { ChangeEvent } from 'react';
import type { ProviderFacadePayload } from '../../api/client';
import { modelOptions, providerOptions } from './providerOptions';
import { SettingsField, SettingsSection } from './SettingsPrimitives';
import { useSettingsProfileContext } from './SettingsProfileContext';

function optionsWithCurrent(options: Array<{ id: string; label: string }>, current: string) {
  return current && !options.some((option) => option.id === current) ? [{ id: current, label: `${current} (unavailable)` }, ...options] : options;
}

function updateString(dispatch: ReturnType<typeof useSettingsProfileContext>['dispatch'], path: string) {
  return (event: ChangeEvent<HTMLInputElement | HTMLSelectElement>) => dispatch({ type: 'update', path, value: event.currentTarget.value });
}

function updateNumber(dispatch: ReturnType<typeof useSettingsProfileContext>['dispatch'], path: string) {
  return (event: ChangeEvent<HTMLInputElement>) => dispatch({ type: 'update', path, value: Number(event.currentTarget.value) });
}

function updateBoolean(dispatch: ReturnType<typeof useSettingsProfileContext>['dispatch'], path: string) {
  return (event: ChangeEvent<HTMLInputElement>) => dispatch({ type: 'update', path, value: event.currentTarget.checked });
}

export function ProviderDefaultsSection({ payload }: { payload?: ProviderFacadePayload }) {
  const { state, dispatch } = useSettingsProfileContext();
  const providers = state.draft.global.providers;
  const models = state.draft.global.models;
  const configs = state.draft.providerConfigs;
  const llmOptions = optionsWithCurrent(providerOptions(payload, 'chat'), providers.llm);
  const chatModels = optionsWithCurrent(modelOptions(payload, providers.llm), models.chat);
  const ttsOptions = optionsWithCurrent(providerOptions(payload, 'tts'), providers.tts);
  const sttOptions = optionsWithCurrent(providerOptions(payload, 'stt'), providers.stt);
  const imageOptions = optionsWithCurrent(providerOptions(payload, 'image'), providers.image);
  const imageProviderId = providers.image.replace(/^image:/, '');

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
      <div className="provider-config-grid">
        {providers.llm === 'lmstudio' ? (
          <div className="provider-config-group">
            <h4>LM Studio</h4>
            <div className="settings-form-grid">
              <SettingsField label="Base URL"><input value={configs.lmstudio.baseUrl} onChange={updateString(dispatch, 'providerConfigs.lmstudio.baseUrl')} /></SettingsField>
              <SettingsField label="Model"><input value={configs.lmstudio.model} onChange={updateString(dispatch, 'providerConfigs.lmstudio.model')} placeholder="Runtime default" /></SettingsField>
              <SettingsField label="Direct mode"><input type="checkbox" checked={configs.lmstudio.direct} onChange={updateBoolean(dispatch, 'providerConfigs.lmstudio.direct')} /></SettingsField>
            </div>
          </div>
        ) : null}
        {providers.llm === 'openrouter' ? (
          <div className="provider-config-group">
            <h4>OpenRouter</h4>
            <div className="settings-form-grid">
              <SettingsField label="API key">
                <input type="password" autoComplete="off" value={configs.openrouter.apiKey} onChange={updateString(dispatch, 'providerConfigs.openrouter.apiKey')} placeholder="Enter API key" />
                <small>Stored with Windows user-scoped encryption. OPENROUTER_API_KEY overrides this value.</small>
              </SettingsField>
              <SettingsField label="Model"><input value={configs.openrouter.model} onChange={updateString(dispatch, 'providerConfigs.openrouter.model')} /></SettingsField>
              <SettingsField label="Context size"><input type="number" min={1024} step={1024} value={configs.openrouter.contextSize} onChange={updateNumber(dispatch, 'providerConfigs.openrouter.contextSize')} /></SettingsField>
              <SettingsField label="Thinking budget"><input type="number" min={0} value={configs.openrouter.thinkingBudget} onChange={updateNumber(dispatch, 'providerConfigs.openrouter.thinkingBudget')} /></SettingsField>
            </div>
          </div>
        ) : null}
        {providers.llm === 'cerebras' ? (
          <div className="provider-config-group">
            <h4>Cerebras</h4>
            <div className="settings-form-grid">
              <SettingsField label="API key">
                <input type="password" autoComplete="off" value={configs.cerebras.apiKey} onChange={updateString(dispatch, 'providerConfigs.cerebras.apiKey')} placeholder="Enter API key" />
                <small>Stored with Windows user-scoped encryption. CEREBRAS_API_KEY overrides this value.</small>
              </SettingsField>
              <SettingsField label="Model"><input value={configs.cerebras.model} onChange={updateString(dispatch, 'providerConfigs.cerebras.model')} /></SettingsField>
            </div>
          </div>
        ) : null}
        {providers.llm === 'llamacpp' ? (
          <div className="provider-config-group">
            <h4>llama.cpp</h4>
            <div className="settings-form-grid">
              <SettingsField label="Base URL"><input value={configs.llamacpp.baseUrl} onChange={updateString(dispatch, 'providerConfigs.llamacpp.baseUrl')} /></SettingsField>
              <SettingsField label="Model"><input value={configs.llamacpp.model} onChange={updateString(dispatch, 'providerConfigs.llamacpp.model')} placeholder="Loaded model" /></SettingsField>
              <SettingsField label="Download location"><input value={configs.llamacpp.downloadLocation} onChange={updateString(dispatch, 'providerConfigs.llamacpp.downloadLocation')} /></SettingsField>
              <SettingsField label="Auto start"><input type="checkbox" checked={configs.llamacpp.autoStart} onChange={updateBoolean(dispatch, 'providerConfigs.llamacpp.autoStart')} /></SettingsField>
            </div>
          </div>
        ) : null}
        {providers.tts === 'faster-qwen3-tts' ? (
          <div className="provider-config-group">
            <h4>Faster Qwen3 TTS</h4>
            <div className="settings-form-grid">
              <SettingsField label="Model name"><input value={configs.fasterQwen3Tts.modelName} onChange={updateString(dispatch, 'providerConfigs.fasterQwen3Tts.modelName')} /></SettingsField>
              <SettingsField label="Model directory"><input value={configs.fasterQwen3Tts.modelDir} onChange={updateString(dispatch, 'providerConfigs.fasterQwen3Tts.modelDir')} placeholder="Default cache" /></SettingsField>
              <SettingsField label="Device"><input value={configs.fasterQwen3Tts.device} onChange={updateString(dispatch, 'providerConfigs.fasterQwen3Tts.device')} /></SettingsField>
              <SettingsField label="Data type"><input value={configs.fasterQwen3Tts.dtype} onChange={updateString(dispatch, 'providerConfigs.fasterQwen3Tts.dtype')} /></SettingsField>
              <SettingsField label="Chunk size"><input type="number" min={1} value={configs.fasterQwen3Tts.chunkSize} onChange={updateNumber(dispatch, 'providerConfigs.fasterQwen3Tts.chunkSize')} /></SettingsField>
              <SettingsField label="Non-streaming mode"><input type="checkbox" checked={configs.fasterQwen3Tts.nonStreamingMode} onChange={updateBoolean(dispatch, 'providerConfigs.fasterQwen3Tts.nonStreamingMode')} /></SettingsField>
            </div>
          </div>
        ) : null}
        {providers.stt === 'parakeet' ? (
          <div className="provider-config-group">
            <h4>Parakeet STT</h4>
            <div className="settings-form-grid">
              <SettingsField label="Base URL"><input value={configs.parakeet.baseUrl} onChange={updateString(dispatch, 'providerConfigs.parakeet.baseUrl')} /></SettingsField>
            </div>
          </div>
        ) : null}
        {imageProviderId === 'flux_klein' ? (
          <div className="provider-config-group">
            <h4>FLUX.2 [klein] 4B</h4>
            <div className="settings-form-grid">
              <SettingsField label="Enabled"><input type="checkbox" checked={configs.fluxKlein.enabled} onChange={updateBoolean(dispatch, 'providerConfigs.fluxKlein.enabled')} /></SettingsField>
              <SettingsField label="Repository"><input value={configs.fluxKlein.repoId} onChange={updateString(dispatch, 'providerConfigs.fluxKlein.repoId')} /></SettingsField>
              <SettingsField label="Local directory"><input value={configs.fluxKlein.localDir} onChange={updateString(dispatch, 'providerConfigs.fluxKlein.localDir')} placeholder="Default cache" /></SettingsField>
              <SettingsField label="Device"><input value={configs.fluxKlein.device} onChange={updateString(dispatch, 'providerConfigs.fluxKlein.device')} /></SettingsField>
              <SettingsField label="Torch dtype"><input value={configs.fluxKlein.torchDtype} onChange={updateString(dispatch, 'providerConfigs.fluxKlein.torchDtype')} /></SettingsField>
              <SettingsField label="Prefer local files"><input type="checkbox" checked={configs.fluxKlein.preferLocalFiles} onChange={updateBoolean(dispatch, 'providerConfigs.fluxKlein.preferLocalFiles')} /></SettingsField>
              <SettingsField label="Allow repo fallback"><input type="checkbox" checked={configs.fluxKlein.allowRepoFallback} onChange={updateBoolean(dispatch, 'providerConfigs.fluxKlein.allowRepoFallback')} /></SettingsField>
            </div>
          </div>
        ) : null}
      </div>
    </SettingsSection>
  );
}
