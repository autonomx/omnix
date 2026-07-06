import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { AssetListResponse } from '../../api/client';
import { ImageLatestResult } from './ImageLatestResult';

type ImageAsset = AssetListResponse['assets'][number];

const asset = {
  id: 'image:night',
  module: 'image-generation',
  type: 'image',
  mime_type: 'image/png',
  storage_path: 'private/night.png',
  created_at: '2026-07-05T00:00:00Z',
  metadata: {
    title: 'Night harbor',
    width: 1024,
    height: 768,
    provider_key: 'flux_klein',
  },
} as ImageAsset;

describe('ImageLatestResult', () => {
  it('announces completed results and exposes asset-id actions', () => {
    render(<MantineProvider><ImageLatestResult asset={asset} /></MantineProvider>);

    const region = screen.getByRole('region', { name: 'Latest result' });
    expect(region).toHaveAttribute('aria-live', 'polite');
    expect(region).toHaveAttribute('aria-atomic', 'true');
    expect(screen.getByRole('img', { name: 'Night harbor' })).toHaveAttribute(
      'src',
      '/api/assets/image%3Anight/file',
    );
    expect(screen.getByRole('link', { name: 'Open Night harbor in a new tab' })).toHaveAttribute(
      'href',
      '/api/assets/image%3Anight/file',
    );
    expect(screen.getByRole('link', { name: 'Download Night harbor' })).toHaveAttribute(
      'href',
      '/api/assets/image%3Anight/file?download=true',
    );
    expect(region).not.toHaveTextContent('private/night.png');
  });

  it('announces the empty state', () => {
    render(<MantineProvider><ImageLatestResult /></MantineProvider>);

    expect(screen.getByRole('status')).toHaveTextContent('Generate an image to see the latest result here.');
  });
});
