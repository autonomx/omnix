import { Text, UnstyledButton } from '@mantine/core';
import { useMemo, useState } from 'react';
import type { AssetListResponse } from '../../api/client';

export type ImageAsset = AssetListResponse['assets'][number];

interface ImageAssetGalleryProps {
  assets: ImageAsset[];
  selectedAssetId: string | null;
  onSelect: (assetId: string) => void;
}

export function ImageAssetGallery({ assets, selectedAssetId, onSelect }: ImageAssetGalleryProps) {
  const [query, setQuery] = useState('');
  const [provider, setProvider] = useState('');
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid');
  const providers = useMemo(
    () => [...new Set(assets.map(imageAssetProvider).filter(Boolean))].sort(),
    [assets],
  );
  const visibleAssets = useMemo(
    () => filterImageAssets(assets, query, provider),
    [assets, provider, query],
  );

  return (
    <>
      <div className="image-assets-toolbar">
        <label className="image-assets-search">
          <span aria-hidden="true">⌕</span>
          <span className="visually-hidden">Search image assets</span>
          <input value={query} onChange={(event) => setQuery(event.currentTarget.value)} placeholder="Search assets..." />
        </label>
        <div className="image-view-toggle" role="group" aria-label="Asset view">
          <button type="button" className={viewMode === 'grid' ? 'active' : ''} aria-pressed={viewMode === 'grid'} aria-label="Grid view" onClick={() => setViewMode('grid')}>▦</button>
          <button type="button" className={viewMode === 'list' ? 'active' : ''} aria-pressed={viewMode === 'list'} aria-label="List view" onClick={() => setViewMode('list')}>☷</button>
        </div>
        <label className="image-provider-filter">
          <span aria-hidden="true">▽</span>
          <span className="visually-hidden">Filter image assets by provider</span>
          <select value={provider} onChange={(event) => setProvider(event.currentTarget.value)}>
            <option value="">Filters</option>
            {providers.map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
        </label>
      </div>

      <Text className="image-assets-count" aria-live="polite" role="status" size="xs">
        Showing {visibleAssets.length} of {assets.length} image{assets.length === 1 ? '' : 's'}.
      </Text>

      {!assets.length ? (
        <div className="image-empty-state" role="status"><span aria-hidden="true">▣</span><strong>No image assets yet</strong><small>Generated images will be saved here.</small></div>
      ) : visibleAssets.length ? (
        <div className={`image-assets-grid ${viewMode}`} aria-label="Image asset gallery">
          {visibleAssets.map((asset) => {
            const title = imageAssetTitle(asset);
            const selected = asset.id === selectedAssetId;
            return (
              <UnstyledButton
                aria-label={`Select ${title}`}
                aria-pressed={selected}
                className={`image-asset-card ${selected ? 'selected' : ''}`}
                key={asset.id}
                onClick={() => onSelect(asset.id)}
              >
                <div className="image-asset-preview">
                  <img alt="" loading="lazy" src={imageAssetUrl(asset.id)} />
                  {selected ? <span className="image-asset-selected" aria-hidden="true">★</span> : null}
                </div>
                <div className="image-asset-copy">
                  <strong title={title}>{title}</strong>
                  <small>{imageAssetDimensions(asset)} · {relativeCreatedAt(asset.created_at)}</small>
                  <span aria-hidden="true">•••</span>
                </div>
              </UnstyledButton>
            );
          })}
        </div>
      ) : (
        <div className="image-empty-state" role="status">No image assets match these filters.</div>
      )}
    </>
  );
}

export function filterImageAssets(assets: ImageAsset[], query: string, provider: string): ImageAsset[] {
  const normalizedQuery = query.trim().toLowerCase();
  return assets.filter((asset) => {
    if (provider && imageAssetProvider(asset) !== provider) return false;
    if (!normalizedQuery) return true;
    return [imageAssetTitle(asset), metadataString(asset, 'prompt'), imageAssetProvider(asset)]
      .join(' ')
      .toLowerCase()
      .includes(normalizedQuery);
  });
}

function imageAssetTitle(asset: ImageAsset): string {
  return metadataString(asset, 'title') || metadataString(asset, 'prompt') || 'Generated image';
}

function imageAssetProvider(asset: ImageAsset): string {
  return metadataString(asset, 'provider_key') || metadataString(asset, 'provider_id');
}

function imageAssetDimensions(asset: ImageAsset): string {
  const width = metadataNumber(asset, 'width');
  const height = metadataNumber(asset, 'height');
  return width && height ? `${width} × ${height}` : asset.mime_type;
}

function metadataString(asset: ImageAsset, key: string): string {
  const value = asset.metadata?.[key];
  return typeof value === 'string' ? value : '';
}

function metadataNumber(asset: ImageAsset, key: string): number | undefined {
  const value = asset.metadata?.[key];
  return typeof value === 'number' ? value : undefined;
}

function imageAssetUrl(assetId: string): string {
  return `/api/assets/${encodeURIComponent(assetId)}/file`;
}

function relativeCreatedAt(createdAt: string): string {
  const elapsed = Date.now() - new Date(createdAt).getTime();
  if (!Number.isFinite(elapsed) || elapsed < 0) return 'Just now';
  const minutes = Math.floor(elapsed / 60_000);
  if (minutes < 1) return 'Just now';
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}
