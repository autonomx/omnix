import { Group, Text, UnstyledButton } from '@mantine/core';
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
  const providers = useMemo(
    () => [...new Set(assets.map(imageAssetProvider).filter(Boolean))].sort(),
    [assets],
  );
  const visibleAssets = useMemo(
    () => filterImageAssets(assets, query, provider),
    [assets, provider, query],
  );

  if (!assets.length) {
    return <div className="platform-empty" role="status">No image assets indexed.</div>;
  }

  return (
    <>
      <div className="feature-form" style={{ marginBottom: '1rem' }}>
        <label>
          Search images
          <input value={query} onChange={(event) => setQuery(event.currentTarget.value)} placeholder="Prompt, title, or provider" />
        </label>
        <label>
          Filter by provider
          <select value={provider} onChange={(event) => setProvider(event.currentTarget.value)}>
            <option value="">All providers</option>
            {providers.map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
        </label>
      </div>
      {visibleAssets.length ? (
        <div className="platform-grid" aria-label="Image asset gallery">
          {visibleAssets.map((asset) => {
            const title = imageAssetTitle(asset);
            const selected = asset.id === selectedAssetId;
            return (
              <UnstyledButton
                aria-label={`Select ${title}`}
                aria-pressed={selected}
                key={asset.id}
                onClick={() => onSelect(asset.id)}
                style={{
                  border: selected ? '2px solid var(--mantine-primary-color-filled)' : '1px solid var(--mantine-color-dark-4)',
                  borderRadius: '0.75rem',
                  overflow: 'hidden',
                  textAlign: 'left',
                }}
              >
                <img
                  alt={title}
                  loading="lazy"
                  src={imageAssetUrl(asset.id)}
                  style={{ aspectRatio: '1 / 1', display: 'block', objectFit: 'cover', width: '100%' }}
                />
                <div style={{ padding: '0.75rem' }}>
                  <strong>{title}</strong>
                  <Group gap="xs" mt="xs">
                    <Text size="xs">{imageAssetProvider(asset) || 'Default provider'}</Text>
                    <Text size="xs">{imageAssetDimensions(asset)}</Text>
                  </Group>
                </div>
              </UnstyledButton>
            );
          })}
        </div>
      ) : (
        <div className="platform-empty" role="status">No image assets match these filters.</div>
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
