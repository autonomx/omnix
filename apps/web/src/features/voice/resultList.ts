import type { AssetListResponse } from '../../api/client';

type AssetRecord = AssetListResponse['assets'][number];

export function firstResultAsset(assets: AssetRecord[]): AssetRecord | undefined {
  return assets.find((asset) => asset.type === 'audio');
}
