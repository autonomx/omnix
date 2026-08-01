import { MantineProvider } from '@mantine/core';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { omnixTheme } from '../../design/theme';
import { ImageModelControl, type ImageModelStatusPayload } from './ImageModelSelectorControl';
import {
  buildImageGenerateInput,
  imageRequestDefaultValues,
  resolveImageRequestDefaults,
} from './imageRequestModel';

afterEach(() => {
  vi.unstubAllGlobals();
});

function renderControl(
  status: ImageModelStatusPayload,
  overrides: Partial<Parameters<typeof ImageModelControl>[0]> = {},
) {
  const props = {
    status,
    selectedProvider: status.provider,
    statusLoading: false,
    action: null,
    onSelect: vi.fn(),
    onDownload: vi.fn(),
    onLoad: vi.fn(),
    onUnload: vi.fn(),
    onRefresh: vi.fn(),
    ...overrides,
  };
  render(
    <MantineProvider theme={omnixTheme} defaultColorScheme="dark">
      <ImageModelControl {...props} />
    </MantineProvider>,
  );
  return props;
}

it('selects another image model without downloading or loading it', () => {
  const onSelect = vi.fn();
  const onDownload = vi.fn();
  const onLoad = vi.fn();
  const status: ImageModelStatusPayload = {
    ok: true,
    service: 'image',
    enabled: true,
    provider: 'flux_klein',
    model: 'FLUX.2 [klein] 4B',
    loaded: false,
    state: 'unloaded',
    local_model: { complete: true },
    models: [
      {
        provider: 'flux_klein',
        model: 'FLUX.2 [klein] 4B',
        loaded: false,
        state: 'unloaded',
        local_model: { complete: true },
      },
      {
        provider: 'krea2_turbo',
        model: 'Krea 2 Turbo',
        loaded: false,
        state: 'unloaded',
        supports_download: true,
        local_model: { complete: false, missing: ['model_index.json'] },
      },
    ],
  };

  renderControl(status, { onSelect, onDownload, onLoad });

  fireEvent.change(screen.getByRole('combobox', { name: 'Image model' }), {
    target: { value: 'krea2_turbo' },
  });

  expect(onSelect).toHaveBeenCalledWith('krea2_turbo');
  expect(onDownload).not.toHaveBeenCalled();
  expect(onLoad).not.toHaveBeenCalled();
});

it('shows Download Model and starts the service automatically before downloading', async () => {
  const onRefresh = vi.fn();
  const onDownload = vi.fn();
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    statusText: 'OK',
    json: async () => ({ ok: true, state: 'unloaded' }),
  } as Response);
  vi.stubGlobal('fetch', fetchMock);

  const status: ImageModelStatusPayload = {
    ok: false,
    service: 'image',
    enabled: true,
    provider: 'z_image_turbo',
    model: 'Z-Image Turbo',
    loaded: false,
    state: 'unavailable',
    error: 'image_service_unreachable',
    supports_download: true,
    local_model: { complete: false, missing: ['model_index.json'] },
  };

  renderControl(status, { onRefresh, onDownload });

  expect(screen.queryByRole('button', { name: 'Start Image Service' })).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'Download Model' }));

  await waitFor(() => {
    expect(fetchMock).toHaveBeenCalledWith('/api/image-generation/service/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ provider: 'z_image_turbo' }),
    });
    expect(onRefresh).toHaveBeenCalledTimes(1);
    expect(onDownload).toHaveBeenCalledWith('z_image_turbo');
  });
});

it('shows Start Image Service when model files already exist', () => {
  const status: ImageModelStatusPayload = {
    ok: false,
    service: 'image',
    enabled: true,
    provider: 'flux_klein',
    model: 'FLUX.2 [klein] 4B',
    loaded: false,
    state: 'unavailable',
    error: 'image_service_unreachable',
    supports_download: true,
    downloaded: true,
    local_model: { complete: true },
  };

  renderControl(status);

  expect(screen.getByRole('button', { name: 'Start Image Service' })).toBeEnabled();
  expect(screen.queryByRole('button', { name: 'Download Model' })).toBeNull();
});

it('shows byte and percentage progress while a model downloads', () => {
  const status: ImageModelStatusPayload = {
    ok: false,
    service: 'image',
    enabled: true,
    provider: 'z_image_turbo',
    model: 'Z-Image Turbo',
    loaded: false,
    state: 'downloading',
    supports_download: true,
    local_model: { complete: false },
    download_progress: {
      status: 'downloading',
      bytes_downloaded: 5 * 1024 * 1024 * 1024,
      bytes_total: 20 * 1024 * 1024 * 1024,
      percent: 25,
      indeterminate: false,
    },
  };

  renderControl(status, {
    action: { type: 'download', provider: 'z_image_turbo' },
  });

  expect(screen.getByLabelText('Model download progress bar')).toHaveAttribute('aria-valuenow', '25');
  expect(screen.getByText(/5\.00 GB of 20\.0 GB · 25\.0%/)).toBeInTheDocument();
});

it('uses model-specific generation defaults', () => {
  const base = {
    width: 768,
    height: 768,
    unloadAfterGeneration: false,
  };

  const krea = imageRequestDefaultValues({ ...base, providerId: 'image:krea2_turbo' });
  const zImage = imageRequestDefaultValues({ ...base, providerId: 'image:z_image_turbo' });
  const flux = imageRequestDefaultValues({ ...base, providerId: 'image:flux_klein' });

  expect(flux.steps).toBe('4');
  expect(flux.guidanceScale).toBe('1');
  expect(krea.steps).toBe('8');
  expect(krea.guidanceScale).toBe('0');
  expect(zImage.steps).toBe('9');
  expect(zImage.guidanceScale).toBe('0');
});

it('removes reference assets for text-to-image-only models', () => {
  const defaults = {
    providerId: 'image:krea2_turbo',
    width: 768,
    height: 768,
    unloadAfterGeneration: false,
  };
  const values = {
    ...imageRequestDefaultValues(defaults),
    prompt: 'city',
    referenceAssetIds: ['image:reference'],
  };

  const input = buildImageGenerateInput(values, defaults);
  const resolved = resolveImageRequestDefaults(defaults);

  expect(resolved.supportsImageToImage).toBe(false);
  expect(input.reference_asset_ids).toEqual([]);
  expect(input.no_cache).toBe(false);
});
