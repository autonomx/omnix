import type { ProviderFacadePayload } from '../../api/client';

export type ProviderOption = { id: string; label: string };

export function providerOptions(payload: ProviderFacadePayload | undefined, capability: string): ProviderOption[] {
  return (payload?.providers ?? [])
    .filter((provider) => provider.capabilities.some((item) => item === capability) || provider.family === capability)
    .map((provider) => ({ id: provider.id, label: provider.label || provider.id }))
    .sort((left, right) => left.label.localeCompare(right.label));
}

export function modelOptions(payload: ProviderFacadePayload | undefined, providerId: string, capability = 'chat'): ProviderOption[] {
  return (payload?.models ?? [])
    .filter((model) => (!providerId || model.provider_id === providerId) && model.capabilities.some((item) => item === capability))
    .map((model) => ({ id: model.id, label: model.label || model.id }))
    .sort((left, right) => left.label.localeCompare(right.label));
}
