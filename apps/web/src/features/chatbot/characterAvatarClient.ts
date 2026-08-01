import type { CharacterAvatarPack } from './characterClient';

export type AvatarGenerationStatus = 'queued' | 'generating_base' | 'generating_variants' | 'completed' | 'failed';
export type VisemeGenerationStatus = 'generating' | 'completed' | 'failed';

export interface CreateCharacterAvatarGenerationInput {
  appearance_prompt?: string;
  style?: string;
  outfit_prompt?: string;
  background_prompt?: string;
  provider_id?: string;
  width?: number;
  height?: number;
  seed?: number | null;
  steps?: number;
  guidance_scale?: number | null;
  include_blink?: boolean;
  include_expressions?: boolean;
  include_outfit?: boolean;
  include_background?: boolean;
  unload_after_generation?: boolean;
  source_asset_id?: string;
  source_image_consent_confirmed?: boolean;
}

export interface CharacterAvatarGenerationBatch {
  id: string;
  character_id: string;
  status: AvatarGenerationStatus;
  request: Required<Omit<CreateCharacterAvatarGenerationInput, 'seed' | 'guidance_scale'>> & {
    seed?: number | null;
    guidance_scale?: number | null;
  };
  base_job_id: string;
  variant_job_ids: Record<string, string>;
  asset_ids: Record<string, string>;
  avatar_pack_version?: number | null;
  error: string;
  created_at: string;
  updated_at: string;
}

export interface CharacterVisemeGenerationBatch {
  id: string;
  character_id: string;
  status: VisemeGenerationStatus;
  job_ids: Record<string, string>;
  asset_ids: Record<string, string>;
  attempts: Record<string, number>;
  quality_fallbacks: Record<string, string>;
  avatar_pack_version?: number | null;
  error: string;
  created_at: string;
  updated_at: string;
}

export interface ClonedVoiceBackfillItem {
  voice_asset_id: string;
  display_name: string;
  character_id?: string | null;
  result: 'created' | 'existing' | 'queued' | 'already_has_avatar' | 'skipped' | 'failed';
  generation_batch_id?: string | null;
  reason: string;
}

export interface ClonedVoiceBackfillResponse {
  items: ClonedVoiceBackfillItem[];
}

export interface UploadedAvatarSourceAsset {
  id: string;
  module: string;
  type: 'image';
  mime_type: string;
  storage_path: string;
  metadata: Record<string, unknown>;
}

export interface Live2DModelCatalogItem {
  id: string;
  name: string;
  description: string;
  preview_url: string;
  repository: string;
  revision: string;
  source_url: string;
  model_license_url: string;
  runtime_license_url: string;
  license_summary: string;
  installed: boolean;
  selected: boolean;
}

export interface Live2DModelCatalogResponse {
  models: Live2DModelCatalogItem[];
  runtime_installed: boolean;
}

export interface Live2DAvatarActionResponse {
  ok: boolean;
  character_id: string;
  avatar_pack?: CharacterAvatarPack | null;
  downloaded: boolean;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  if (!response.ok) {
    const responseBody = await response.text();
    let message = responseBody;
    try {
      const payload = JSON.parse(responseBody) as { detail?: unknown };
      if (typeof payload.detail === 'string') message = payload.detail;
    } catch {
      // Keep the raw response when the server did not return JSON.
    }
    throw new Error(message || `Avatar request failed with status ${response.status}.`);
  }
  return response.json() as Promise<T>;
}

function jsonInit(method: string, body: unknown): RequestInit {
  return { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) };
}

export const characterAvatarClient = {
  optionalPack(characterId: string): Promise<CharacterAvatarPack | null> {
    return request(`/api/characters/${encodeURIComponent(characterId)}/avatar-pack/optional`);
  },
  async uploadSourceImage(file: File): Promise<UploadedAvatarSourceAsset> {
    const payload = await request<{ ok: true; asset: UploadedAvatarSourceAsset }>(
      `/api/image-generation/references?filename=${encodeURIComponent(file.name || 'avatar-source')}`,
      {
        method: 'POST',
        headers: { 'Content-Type': file.type || 'application/octet-stream' },
        body: file,
      },
    );
    return payload.asset;
  },
  createGeneration(characterId: string, input: CreateCharacterAvatarGenerationInput): Promise<CharacterAvatarGenerationBatch> {
    return request(`/api/characters/${encodeURIComponent(characterId)}/avatar-generations`, jsonInit('POST', input));
  },
  generation(batchId: string): Promise<CharacterAvatarGenerationBatch> {
    return request(`/api/character-avatar-generations/${encodeURIComponent(batchId)}`);
  },
  createVisemeGeneration(characterId: string): Promise<CharacterVisemeGenerationBatch> {
    return request(`/api/characters/${encodeURIComponent(characterId)}/avatar-visemes`, { method: 'POST' });
  },
  visemeGeneration(batchId: string): Promise<CharacterVisemeGenerationBatch> {
    return request(`/api/character-avatar-visemes/${encodeURIComponent(batchId)}`);
  },
  live2dCatalog(characterId: string): Promise<Live2DModelCatalogResponse> {
    return request(`/api/characters/${encodeURIComponent(characterId)}/live2d-models`);
  },
  activateLive2d(
    characterId: string,
    input: {
      model_id: string;
      accept_live2d_runtime_terms: boolean;
      accept_model_terms: boolean;
    },
  ): Promise<Live2DAvatarActionResponse> {
    return request(`/api/characters/${encodeURIComponent(characterId)}/live2d-avatar`, jsonInit('POST', input));
  },
  disableLive2d(characterId: string): Promise<Live2DAvatarActionResponse> {
    return request(`/api/characters/${encodeURIComponent(characterId)}/live2d-avatar/disable`, { method: 'POST' });
  },
  backfillClonedVoices(input: {
    queue_avatar_generation?: boolean;
    appearance_template?: string;
    style?: string;
    provider_id?: string;
    include_reference_profiles?: boolean;
  }): Promise<ClonedVoiceBackfillResponse> {
    return request('/api/characters/backfill-cloned-voices', jsonInit('POST', input));
  },
};

export function characterAvatarAssetUrl(assetId: string): string {
  return `/api/assets/${encodeURIComponent(assetId)}/file`;
}
