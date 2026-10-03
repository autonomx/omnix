import type { components } from '../../api/generated/types';

type AssetRecord = components['schemas']['PublicAssetRecord'];

export function firstResultAsset(assets: AssetRecord[]): AssetRecord | undefined {
  return assets.find((asset) => asset.type === 'audio');
}
