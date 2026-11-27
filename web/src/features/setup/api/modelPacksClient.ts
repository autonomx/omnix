import type { JobRecord } from '../../../api/client';
import { omnixApiClient } from '../../../api/client';
import { sendGatewayCall } from '../../../api/http';
import { api } from './gateway';
import type { components } from './generated';

export type ModelPacksStatus = components['schemas']['ModelPacksStatus'];
export type PackVerdict = components['schemas']['PackVerdict'];
export type PackRuntimeStatus = components['schemas']['PackRuntimeStatus'];
export type PackModelStatus = components['schemas']['PackModelStatus'];
export type SelectionSize = components['schemas']['SelectionSize'];
export type CapabilitiesResponse = components['schemas']['CapabilitiesResponse'];
export type PackTarget = components['schemas']['PackTarget'];
export type PackOption = components['schemas']['PackOption'];
export type DefaultModels = components['schemas']['DefaultModels'];

export type AvatarLibrary = components['schemas']['Live2DModelCatalogResponse'];
export type AvatarModel = components['schemas']['Live2DModelCatalogItem'];
export type AssistantDefaults = components['schemas']['AssistantDefaults'];
export type AssistantDefaultsApplied = components['schemas']['AssistantDefaultsApplied'];

export const MODEL_PACKS_QUERY_KEY = ['setup', 'model-packs'] as const;
export const AVATARS_QUERY_KEY = ['setup', 'avatars'] as const;
export const ASSISTANT_DEFAULTS_QUERY_KEY = ['setup', 'assistant-defaults'] as const;
export const CAPABILITIES_QUERY_KEY = ['setup', 'capabilities'] as const;

/** The Live2D avatars Omnix can download (any character can then use one). */
export const avatarsClient = {
  async library(): Promise<AvatarLibrary> {
    return sendGatewayCall(() => api.GET('/api/character-live2d/models'));
  },

  async install(modelId: string): Promise<AvatarLibrary> {
    return sendGatewayCall(() => api.POST('/api/character-live2d/models/{model_id}', {
      params: { path: { model_id: modelId } },
      body: { accept_live2d_runtime_terms: true, accept_model_terms: true },
    }));
  },

  async remove(modelId: string): Promise<AvatarLibrary> {
    return sendGatewayCall(() => api.DELETE('/api/character-live2d/models/{model_id}', { params: { path: { model_id: modelId } } }));
  },
};

/**
 * The System Assistant's first-run defaults the installer ships: a live portrait and the Maya voice. Applying them
 * never replaces an avatar or a voice the owner chose.
 */
export const assistantDefaultsClient = {
  async status(): Promise<AssistantDefaults> {
    return sendGatewayCall(() => api.GET('/api/assistant-defaults'));
  },

  async apply(): Promise<AssistantDefaultsApplied> {
    return sendGatewayCall(() => api.POST('/api/assistant-defaults'));
  },
};

/** The shipped portrait, for setup's preview. */
export const ASSISTANT_PORTRAIT_URL = '/api/assistant-defaults/portrait';

/** The setup screen's gateway calls (desktop roadmap §4.5). */
export const modelPacksClient = {
  async status(): Promise<ModelPacksStatus> {
    return sendGatewayCall(() => api.GET('/api/model-packs'));
  },

  async selection(bundles: string[], options: Record<string, string[]> = {}): Promise<SelectionSize> {
    return sendGatewayCall(() => api.POST('/api/model-packs/selection', { body: { bundles, options } }));
  },

  async setDefaults(defaults: { voice?: string; image?: string }): Promise<DefaultModels> {
    return sendGatewayCall(() => api.POST('/api/model-packs/defaults', { body: { voice: defaults.voice ?? '', image: defaults.image ?? '' } }));
  },

  async capabilities(): Promise<CapabilitiesResponse> {
    return sendGatewayCall(() => api.GET('/api/model-packs/capabilities'));
  },

  async install(target: PackTarget): Promise<JobRecord> {
    return sendGatewayCall(() => api.POST('/api/model-packs/install', { body: target })) as Promise<JobRecord>;
  },

  async remove(target: PackTarget): Promise<JobRecord> {
    return sendGatewayCall(() => api.POST('/api/model-packs/remove', { body: target })) as Promise<JobRecord>;
  },

  async verify(target: PackTarget): Promise<JobRecord> {
    return sendGatewayCall(() => api.POST('/api/model-packs/verify', { body: target })) as Promise<JobRecord>;
  },

  async job(jobId: string): Promise<JobRecord> {
    return omnixApiClient.getJob(jobId);
  },

  async cancel(jobId: string): Promise<JobRecord> {
    return omnixApiClient.cancelJob(jobId, 'cancelled from the setup screen');
  },
};

/** `bytes` as GB with one decimal (the units the setup screen and the roadmap use). */
export function formatGigabytes(bytes: number): string {
  return `${(bytes / 1e9).toFixed(1)} GB`;
}
