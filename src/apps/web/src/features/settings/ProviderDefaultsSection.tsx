import { useEffect, useState, type ChangeEvent } from 'react';
import { omnixApiClient, type CodexAuthStatus, type ProviderFacadePayload } from '../../api/client';
import { modelOptions, providerOptions } from './providerOptions';
import { SettingsField, SettingsSection } from './SettingsPrimitives';
import { useSettingsProfileContext } from './SettingsProfileContext';

const defaultReasoningEffortOptions = [
  { id: 'none', label: 'Instant (none)' },
  { id: 'low', label: 'low' },
  { id: 'medium', label: 'medium' },
  { id: 'high', label: 'high' },
];

function optionsWithCurrent(options: Array<{ id: string; label: string }>, current: string) {
  return current && !options.some((option) => option.id === current) ? [{ id: current, label: `${current} (unavailable)` }, ...options] : options;
}

function codexModelId(model: ProviderFacadePayload['models'][number]): string {
  const metadata = model.metadata as Record<string, unknown> | undefined;
  const metadataId = typeof metadata?.model_id === 'string' ? metadata.model_id.trim() : '';
  return metadataId || model.id.replace(/^llm:chatgpt_codex:/, '');
}

function codexModelOptions(payload: ProviderFacadePayload | undefined, current: string) {
  const options = (payload?.models ?? [])
    .filter((model) => model.provider_id === 'llm:chatgpt_codex')
    .map((model) => ({ id: codexModelId(model), label: model.label || codexModelId(model) }))
    .filter((option, index, all) => option.id && all.findIndex((candidate) => candidate.id === option.id) === index);
  return optionsWithCurrent(options, current);
}

function reasoningEffortId(value: unknown): string {
  if (typeof value === 'string') return value.trim();
  if (!value || typeof value !== 'object' || Array.isArray(value)) return '';
  const row = value as Record<string, unknown>;
  for (const key of ['effort', 'id', 'value', 'name']) {
    if (typeof row[key] === 'string' && row[key].trim()) return row[key].trim();
  }
  return '';
}

function codexReasoningOptions(payload: ProviderFacadePayload | undefined, modelId: string, current: string) {
  const model = (payload?.models ?? []).find((candidate) => (
    candidate.provider_id === 'llm:chatgpt_codex' && codexModelId(candidate) === modelId
  ));
  const metadata = model?.metadata as Record<string, unknown> | undefined;
  const supported = Array.isArray(metadata?.supported_reasoning_efforts)
    ? metadata.supported_reasoning_efforts.map(reasoningEffortId).filter(Boolean)
    : [];
  const options = supported.length
    ? [...new Set(supported)].map((id) => ({ id, label: id === 'none' ? 'Instant (none)' : id }))
    : defaultReasoningEffortOptions;
  return optionsWithCurrent(options, current);
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

function codexAuthLabel(status: CodexAuthStatus): string {
  if (!status.installed) return 'Codex CLI not found';
  if (!status.authenticated) return 'Not signed in';
  if (status.auth_mode === 'chatgpt') return 'Signed in with ChatGPT';
  if (status.auth_mode === 'api_key') return 'Signed in with API key';
  return 'Signed in';
}

export function ProviderDefaultsSection({ payload }: { payload?: ProviderFacadePayload }) {
  const { state, dispatch } = useSettingsProfileContext();
  const [codexAuthStatus, setCodexAuthStatus] = useState<CodexAuthStatus>();
  const [codexAuthBusy, setCodexAuthBusy] = useState<'login' | 'check' | null>(null);
  const [codexAuthMessage, setCodexAuthMessage] = useState('');
  const [codexCatalogPayload, setCodexCatalogPayload] = useState<ProviderFacadePayload>();
  const providers = state.draft.global.providers;
  const models = state.draft.global.models;
  const configs = state.draft.providerConfigs;
  const effectivePayload = providers.llm === 'chatgpt_codex' ? codexCatalogPayload ?? payload : payload;
  const llmOptions = optionsWithCurrent(providerOptions(payload, 'chat'), providers.llm);
  const chatModels = optionsWithCurrent(modelOptions(effectivePayload, providers.llm), models.chat);
  const ttsOptions = optionsWithCurrent(providerOptions(payload, 'tts'), providers.tts);
  const sttOptions = optionsWithCurrent(providerOptions(payload, 'stt'), providers.stt);
  const imageOptions = optionsWithCurrent(providerOptions(payload, 'image'), providers.image);
  const imageProviderId = providers.image.replace(/^image:/, '');
  const codexModels = codexModelOptions(effectivePayload, configs.chatgptCodex.model);
  const reasoningEffortOptions = codexReasoningOptions(
    effectivePayload,
    configs.chatgptCodex.model,
    configs.chatgptCodex.reasoningEffort,
  );

  useEffect(() => {
    if (providers.llm !== 'chatgpt_codex') return;
    let active = true;
    void omnixApiClient.getCodexAuthStatus().then((status) => {
      if (active) setCodexAuthStatus(status);
    }).catch((error: unknown) => {
      if (active) setCodexAuthMessage(error instanceof Error ? error.message : 'Unable to check Codex login.');
    });
    void omnixApiClient.listModels().then((catalog) => {
      if (active) setCodexCatalogPayload(catalog);
    }).catch(() => undefined);
    return () => { active = false; };
  }, [providers.llm]);

  const refreshCodexCatalog = () => {
    void omnixApiClient.listModels().then(setCodexCatalogPayload).catch(() => undefined);
  };

  const checkCodexLogin = async (action: 'login' | 'check') => {
    setCodexAuthBusy(action);
    setCodexAuthMessage('');
    try {
      const status = action === 'login'
        ? await omnixApiClient.startCodexLogin()
        : await omnixApiClient.getCodexAuthStatus();
      setCodexAuthStatus(status);
      if (status.authenticated) refreshCodexCatalog();
      if (action === 'login' && status.started) {
        setCodexAuthMessage('Browser sign-in opened. Complete it, then click Check login.');
      } else if (action === 'login' && !status.installed) {
        setCodexAuthMessage(status.detail || 'Install Codex CLI before signing in.');
      }
    } catch (error: unknown) {
      setCodexAuthMessage(error instanceof Error ? error.message : 'Unable to start Codex login.');
    } finally {
      setCodexAuthBusy(null);
    }
  };

  const handleLlmProviderChange = (event: ChangeEvent<HTMLSelectElement>) => {
    const nextProvider = event.currentTarget.value;
    if (nextProvider === providers.llm) return;
    dispatch({ type: 'update', path: 'global.providers.llm', value: nextProvider });
    // Model ids are provider-specific. Clearing every LLM model route prevents a
    // previous local/OpenRouter model id from overriding the newly selected
    // provider's configured default (notably gpt-5.6-sol for ChatGPT Codex).
    for (const key of ['chat', 'fast', 'quality', 'background', 'embedding', 'imagePrompt']) {
      dispatch({ type: 'update', path: `global.models.${key}`, value: '' });
    }
  };

  return (
    <SettingsSection title="Default providers" description="Defaults apply to new sessions and jobs. Module workspaces can override them." scope="global">
      <div className="settings-form-grid">
        <SettingsField label="Default LLM provider">
          <select value={providers.llm} onChange={handleLlmProviderChange}>
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
        {providers.llm === 'chatgpt_codex' ? (
          <div className="provider-config-group">
            <h4>ChatGPT Plus (Codex)</h4>
            <div className="settings-form-grid">
              <SettingsField label="Model">
                <select value={configs.chatgptCodex.model} onChange={updateString(dispatch, 'providerConfigs.chatgptCodex.model')}>
                  {codexModels.map((option) => <option key={option.id} value={option.id}>{option.label}</option>)}
                </select>
                <small>Loaded from the models available to your ChatGPT account through Codex; the configured model remains available if discovery is offline.</small>
              </SettingsField>
              <SettingsField label="Reasoning effort">
                <select value={configs.chatgptCodex.reasoningEffort} onChange={updateString(dispatch, 'providerConfigs.chatgptCodex.reasoningEffort')}>
                  {reasoningEffortOptions.map((option) => <option key={option.id} value={option.id}>{option.label}</option>)}
                </select>
                <small>Uses the selected model's advertised reasoning levels when Codex exposes them.</small>
              </SettingsField>
              <SettingsField label="Fast mode">
                <input
                  type="checkbox"
                  checked={configs.chatgptCodex.fastMode}
                  onChange={updateBoolean(dispatch, 'providerConfigs.chatgptCodex.fastMode')}
                  disabled={configs.chatgptCodex.model !== 'gpt-5.6-sol'}
                />
                <small>Uses Fast service tier for GPT-5.6 Sol. Select Sol to enable this control.</small>
              </SettingsField>
              <SettingsField label="Codex executable">
                <input value={configs.chatgptCodex.codexPath} onChange={updateString(dispatch, 'providerConfigs.chatgptCodex.codexPath')} placeholder="codex" />
              </SettingsField>
              <SettingsField label="Transport">
                <input value={configs.chatgptCodex.transport} readOnly />
                <small>Uses the persistent local Codex app-server stdio transport.</small>
              </SettingsField>
              <SettingsField label="Authentication" wide>
                <div className="settings-inline-actions">
                  <button type="button" className="settings-secondary-button" onClick={() => void checkCodexLogin('login')} disabled={codexAuthBusy !== null}>
                    {codexAuthBusy === 'login' ? 'Opening sign-in…' : 'Log in with ChatGPT'}
                  </button>
                  <button type="button" className="settings-secondary-button" onClick={() => void checkCodexLogin('check')} disabled={codexAuthBusy !== null}>
                    {codexAuthBusy === 'check' ? 'Checking…' : 'Check login'}
                  </button>
                </div>
                {codexAuthStatus ? <small role="status">Codex status: {codexAuthLabel(codexAuthStatus)}.</small> : null}
                {codexAuthMessage ? <small className="settings-inline-status" role="status">{codexAuthMessage}</small> : null}
                <small>Authentication stays in Codex. Omnix never stores the OAuth token.</small>
              </SettingsField>
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
