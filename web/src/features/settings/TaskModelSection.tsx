import type { ProviderFacadePayload } from '../../api/client';
import { modelOptions, optionsWithCurrent, providerOptions } from './providerOptions';
import { SettingsField, SettingsSection } from './SettingsPrimitives';
import { useSettingsProfileContext } from './SettingsProfileContext';

type TaskRoute = { providerId: string; modelId: string };

type TaskModelSectionProps = {
  payload?: ProviderFacadePayload;
  /** The key under ``global.routing.taskOverrides`` the backend reads. */
  routeKey: string;
  title: string;
  description: string;
  providerLabel: string;
  modelLabel: string;
  /** Help under the model field, given the provider in effect and whether a model is chosen. */
  modelHelp?: (provider: string, modelChosen: boolean) => string | undefined;
};

/** Which provider and model one background feature uses. Unset, it follows the default provider. */
export function TaskModelSection({ payload, routeKey, title, description, providerLabel, modelLabel, modelHelp }: TaskModelSectionProps) {
  const { state, dispatch } = useSettingsProfileContext();
  const overrides = state.draft.global.routing.taskOverrides;
  const chosen: TaskRoute = overrides[routeKey] ?? { providerId: '', modelId: '' };
  const defaultProvider = state.draft.global.providers.llm;
  const providers = providerOptions(payload, 'chat');
  const provider = chosen.providerId || defaultProvider;
  const models = optionsWithCurrent(modelOptions(payload, provider), chosen.modelId);
  const defaultLabel = providers.find((option) => option.id === defaultProvider)?.label ?? defaultProvider;

  const choose = (next: TaskRoute) => {
    const rest = Object.fromEntries(Object.entries(overrides).filter(([key]) => key !== routeKey));
    dispatch({
      type: 'update',
      path: 'global.routing.taskOverrides',
      value: next.providerId || next.modelId ? { ...rest, [routeKey]: next } : rest,
    });
  };

  return (
    <SettingsSection title={title} description={description} scope="global">
      <div className="settings-form-grid">
        <SettingsField label={providerLabel}>
          <select value={chosen.providerId} onChange={(event) => choose({ providerId: event.currentTarget.value, modelId: '' })}>
            <option value="">Same as the default: {defaultLabel || 'none'}</option>
            {optionsWithCurrent(providers, chosen.providerId).map((option) => <option key={option.id} value={option.id}>{option.label}</option>)}
          </select>
        </SettingsField>
        <SettingsField label={modelLabel} help={modelHelp?.(provider, Boolean(chosen.modelId))}>
          <select value={chosen.modelId} onChange={(event) => choose({ ...chosen, modelId: event.currentTarget.value })}>
            <option value="">Provider default</option>
            {models.map((option) => <option key={option.id} value={option.id}>{option.label}</option>)}
          </select>
        </SettingsField>
      </div>
    </SettingsSection>
  );
}
