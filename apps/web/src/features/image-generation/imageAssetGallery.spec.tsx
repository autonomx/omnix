import { MantineProvider } from '@mantine/core';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { AssetListResponse } from '../../api/client';
import { ImageAssetGallery, filterImageAssets } from './ImageAssetGallery';

type ImageAsset = AssetListResponse['assets'][number];

const assets = [
  {
    id: 'image:forest',
    module: 'image-generation',
    type: 'image',
    mime_type: 'image/png',
    storage_path: 'forest.png',
    created_at: '2026-07-01T00:00:00Z',
    metadata: { title: 'Forest light', prompt: 'green trees', provider_key: 'flux' },
  },
  {
    id: 'image:city',
    module: 'image-generation',
    type: 'image',
    mime_type: 'image/png',
    storage_path: 'city.png',
    created_at: '2026-07-02T00:00:00Z',
    metadata: { title: 'Night city', prompt: 'neon street', provider_key: 'mock' },
  },
] as ImageAsset[];

describe('ImageAssetGallery', () => {
  it('filters by search and provider', () => {
    expect(filterImageAssets(assets, 'green', '')).toEqual([assets[0]]);
    expect(filterImageAssets(assets, '', 'mock')).toEqual([assets[1]]);
  });

  it('selects a thumbnail', () => {
    const onSelect = vi.fn();
    render(<MantineProvider><ImageAssetGallery assets={assets} selectedAssetId={null} onSelect={onSelect} /></MantineProvider>);

    fireEvent.click(screen.getByRole('button', { name: 'Select Night city' }));

    expect(onSelect).toHaveBeenCalledWith('image:city');
  });
});
