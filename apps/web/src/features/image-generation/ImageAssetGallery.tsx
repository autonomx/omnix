import { Button, Text, UnstyledButton } from '@mantine/core';
import { useQueryClient } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
import { omnixApiClient, type AssetListResponse } from '../../api/client';
import { IMAGE_ASSETS_QUERY_KEY, IMAGE_JOBS_QUERY_KEY, imageAssetUrl } from './imageWorkspaceModel';
import { ImagePreviewDialog } from './ImagePreviewDialog';

export type ImageAsset = AssetListResponse['assets'][number];

interface DeleteImageAssetResponse {
  ok: boolean;
  asset_id: string;
  deleted: boolean;
  file_deleted: boolean;
  file_error?: string;
}

interface ImageAssetGalleryProps {
  assets: ImageAsset[];
  selectedAssetId: string | null;
  onSelect: (assetId: string) => void;
}

export function ImageAssetGallery({ assets, selectedAssetId, onSelect }: ImageAssetGalleryProps) {
  const queryClient = useQueryClient();
  const [query, setQuery] = useState('');
  const [provider, setProvider] = useState('');
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid');
  const [previewAsset, setPreviewAsset] = useState<ImageAsset | null>(null);
  const [deletedAssetIds, setDeletedAssetIds] = useState<Set<string>>(() => new Set());
  const [deletingAssetId, setDeletingAssetId] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState(false);
  const activeAssets = useMemo(
    () => assets.filter((asset) => !deletedAssetIds.has(asset.id)),
    [assets, deletedAssetIds],
  );
  const providers = useMemo(
    () => [...new Set(activeAssets.map(imageAssetProvider).filter(Boolean))].sort(),
    [activeAssets],
  );
  const visibleAssets = useMemo(
    () => filterImageAssets(activeAssets, query, provider),
    [activeAssets, provider, query],
  );
  const hasFilters = Boolean(query.trim() || provider);

  const clearFilters = () => {
    setQuery('');
    setProvider('');
  };

  const requestDelete = async (asset: ImageAsset) => {
    const title = imageAssetTitle(asset);
    const confirmed = typeof window === 'undefined'
      || window.confirm(`Delete “${title}”? This removes the image file and cannot be undone.`);
    if (!confirmed) return;
    if (previewAsset?.id === asset.id) setPreviewAsset(null);
    setDeleteError(false);
    setDeletingAssetId(asset.id);
    try {
      const result = await omnixApiClient.post<Record<string, never>, DeleteImageAssetResponse>(
        `/api/image-generation/assets/${encodeURIComponent(asset.id)}/delete`,
        {},
      );
      if (!result.ok || !result.deleted) throw new Error('image_delete_failed');
      setDeletedAssetIds((current) => new Set(current).add(result.asset_id));
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: IMAGE_ASSETS_QUERY_KEY }),
        queryClient.invalidateQueries({ queryKey: IMAGE_JOBS_QUERY_KEY }),
      ]);
    } catch {
      setDeleteError(true);
    } finally {
      setDeletingAssetId(null);
    }
  };

  return (
    <>
      <div className="image-assets-toolbar">
        <label className="image-assets-search">
          <span aria-hidden="true">⌕</span>
          <span className="visually-hidden">Search images</span>
          <input aria-label="Search images" value={query} onChange={(event) => setQuery(event.currentTarget.value)} placeholder="Search assets..." />
        </label>
        <div className="image-view-toggle" role="group" aria-label="Asset view">
          <button type="button" className={viewMode === 'grid' ? 'active' : ''} aria-pressed={viewMode === 'grid'} aria-label="Grid view" onClick={() => setViewMode('grid')}>▦</button>
          <button type="button" className={viewMode === 'list' ? 'active' : ''} aria-pressed={viewMode === 'list'} aria-label="List view" onClick={() => setViewMode('list')}>☷</button>
        </div>
        <label className="image-provider-filter">
          <span aria-hidden="true">▽</span>
          <span className="visually-hidden">Filter image assets by provider</span>
          <select aria-label="Filter image assets by provider" value={provider} onChange={(event) => setProvider(event.currentTarget.value)}>
            <option value="">All providers</option>
            {providers.map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
        </label>
        {hasFilters ? <button className="image-clear-filters" type="button" onClick={clearFilters}>Clear filters</button> : null}
      </div>

      <Text className="image-assets-count" aria-live="polite" role="status" size="xs">
        Showing {visibleAssets.length} of {activeAssets.length} image{activeAssets.length === 1 ? '' : 's'}.
      </Text>

      {!activeAssets.length ? (
        <div className="image-empty-state" role="status"><span aria-hidden="true">▣</span><strong>No image assets yet</strong><small>Generated images will be saved here.</small></div>
      ) : visibleAssets.length ? (
        <div className={`image-assets-grid ${viewMode}`} aria-label="Image asset gallery">
          {visibleAssets.map((asset) => {
            const title = imageAssetTitle(asset);
            const selected = asset.id === selectedAssetId;
            const deleting = asset.id === deletingAssetId;
            return (
              <article className={`image-asset-card ${selected ? 'selected' : ''}`} key={asset.id}>
                <div className="image-asset-select">
                  <div className="image-asset-preview">
                    <button type="button" aria-label={`Enlarge ${title}`} onClick={() => setPreviewAsset(asset)}>
                      <img alt="" loading="lazy" src={imageAssetUrl(asset.id)} />
                    </button>
                    {selected ? <span className="image-asset-selected" aria-hidden="true">★</span> : null}
                  </div>
                  <UnstyledButton
                    aria-label={`Select ${title}`}
                    aria-pressed={selected}
                    className="image-asset-copy"
                    onClick={() => onSelect(asset.id)}
                  >
                    <strong title={title}>{title}</strong>
                    <small>{imageAssetDimensions(asset)} · {relativeCreatedAt(asset.created_at)}</small>
                  </UnstyledButton>
                </div>
                <div className="image-asset-actions">
                  <Button component="a" href={imageAssetUrl(asset.id)} target="_blank" rel="noreferrer" size="compact-xs" variant="subtle">Open</Button>
                  <Button component="a" href={imageAssetUrl(asset.id, true)} download size="compact-xs" variant="subtle">Download</Button>
                  <Button
                    aria-label={`Delete ${title}`}
                    color="red"
                    disabled={Boolean(deletingAssetId) && !deleting}
                    loading={deleting}
                    onClick={() => void requestDelete(asset)}
                    size="compact-xs"
                    variant="subtle"
                  >
                    Delete
                  </Button>
                </div>
              </article>
            );
          })}
        </div>
      ) : (
        <div className="image-empty-state" role="status">No image assets match these filters.</div>
      )}
      {deleteError ? <Text c="red" size="sm" role="alert">Image deletion failed.</Text> : null}
      {previewAsset ? <ImagePreviewDialog asset={previewAsset} onClose={() => setPreviewAsset(null)} /> : null}
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
