import type { ProviderFacadePayload } from '../../api/client';
import { modelOptions, optionsWithCurrent, providerOptions } from './providerOptions';
import { SettingsField, SettingsSection } from './SettingsPrimitives';
import { useSettingsProfileContext } from './SettingsProfileContext';

/** The routing override memory reads (backend ``assistant_memory.model_route.MEMORY_ROUTE_KEY``). */
export const MEMORY_ROUTE_KEY = 'assistant-memory';

type MemoryRoute = { providerId: string; modelId: string };

/**
 * Which provider and model memory uses: reading chats for what to remember and what each character knows about the
 * person. Unset, it follows the default provider (on the Claude CLI, chats are read with Sonnet).
 */
export function MemoryModelSection({ payload }: { payload?: ProviderFacadePayload }) {
  const { state, dispatch } = useSettingsProfileContext();
  const overrides = state.draft.global.routing.taskOverrides;
  const chosen: MemoryRoute = overrides[MEMORY_ROUTE_KEY] ?? { providerId: '', modelId: '' };
  const defaultProvider = state.draft.global.providers.llm;
  const providers = providerOptions(payload, 'chat');
  const provider = chosen.providerId || defaultProvider;
  const models = optionsWithCurrent(modelOptions(payload, provider), chosen.modelId);
  const defaultLabel = providers.find((option) => option.id === defaultProvider)?.label ?? defaultProvider;

  const choose = (next: MemoryRoute) => {
    const rest = Object.fromEntries(Object.entries(overrides).filter(([key]) => key !== MEMORY_ROUTE_KEY));
    dispatch({
      type: 'update',
      path: 'global.routing.taskOverrides',
      value: next.providerId || next.modelId ? { ...rest, [MEMORY_ROUTE_KEY]: next } : rest,
    });
  };

  return (
    <SettingsSection
      title="Memory model"
      description="Reads your chats after each turn for what to remember and what each character knows about you. It runs in the background, so a slower, smarter model costs no reply time."
      scope="global"
    >
      <div className="settings-form-grid">
        <SettingsField label="Memory provider">
          <select value={chosen.providerId} onChange={(event) => choose({ providerId: event.currentTarget.value, modelId: '' })}>
            <option value="">Same as the default: {defaultLabel || 'none'}</option>
            {optionsWithCurrent(providers, chosen.providerId).map((option) => <option key={option.id} value={option.id}>{option.label}</option>)}
          </select>
        </SettingsField>
        <SettingsField
          label="Memory model"
          help={!chosen.modelId && provider === 'claude_cli' ? 'Provider default: Sonnet reads chats; the Claude CLI model picks memories.' : undefined}
        >
          <select value={chosen.modelId} onChange={(event) => choose({ ...chosen, modelId: event.currentTarget.value })}>
            <option value="">Provider default</option>
            {models.map((option) => <option key={option.id} value={option.id}>{option.label}</option>)}
          </select>
        </SettingsField>
      </div>
    </SettingsSection>
  );
}
