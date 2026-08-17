import { MantineProvider } from '@mantine/core';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { omnixTheme } from '../../design/theme';
import { ImageAssetGallery, type ImageAsset } from './ImageAssetGallery';

const asset = {
  id: 'image:castle',
  module: 'image-generation',
  type: 'image',
  mime_type: 'image/png',
  storage_path: 'generated/castle.png',
  source_job_id: 'job:castle',
  created_at: '2026-07-06T00:00:00Z',
  metadata: {
    title: 'Castle at dusk',
    width: 768,
    height: 768,
    provider_key: 'flux_klein',
  },
  compat: {},
} as ImageAsset;

function renderGallery() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return render(
    <MantineProvider theme={omnixTheme} defaultColorScheme="dark">
      <QueryClientProvider client={queryClient}>
        <ImageAssetGallery assets={[asset]} selectedAssetId={null} onSelect={vi.fn()} />
      </QueryClientProvider>
    </MantineProvider>,
  );
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('ImageAssetGallery deletion', () => {
  it('confirms and requests deletion of the selected image asset', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => Response.json({
      ok: true,
      asset_id: asset.id,
      deleted: true,
      file_deleted: true,
    }));
    vi.stubGlobal('fetch', fetchMock);
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    renderGallery();

    fireEvent.click(screen.getByRole('button', { name: 'Delete Castle at dusk' }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [request, init] = fetchMock.mock.calls[0];
    expect(String(request)).toContain('/api/image-generation/assets/image%3Acastle/delete');
    expect(init?.method).toBe('POST');
    expect(window.confirm).toHaveBeenCalledWith(expect.stringContaining('cannot be undone'));
  });

  it('does not delete when confirmation is declined', () => {
    const fetchMock = vi.fn((_input: RequestInfo | URL, _init?: RequestInit) => Promise.resolve(Response.json({})));
    vi.stubGlobal('fetch', fetchMock);
    vi.spyOn(window, 'confirm').mockReturnValue(false);
    renderGallery();

    fireEvent.click(screen.getByRole('button', { name: 'Delete Castle at dusk' }));

    expect(fetchMock).not.toHaveBeenCalled();
  });
});
