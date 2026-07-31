import { MantineProvider } from '@mantine/core';
import { fireEvent, render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { omnixTheme } from '../../design/theme';
import { ImageModelControl, type ImageModelStatusPayload } from './ImageModelSelectorControl';

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

  render(
    <MantineProvider theme={omnixTheme} defaultColorScheme="dark">
      <ImageModelControl
        status={status}
        selectedProvider="flux_klein"
        statusLoading={false}
        action={null}
        onSelect={onSelect}
        onDownload={onDownload}
        onLoad={onLoad}
        onUnload={vi.fn()}
        onRefresh={vi.fn()}
      />
    </MantineProvider>,
  );

  fireEvent.change(screen.getByRole('combobox', { name: 'Image model' }), {
    target: { value: 'krea2_turbo' },
  });

  expect(onSelect).toHaveBeenCalledWith('krea2_turbo');
  expect(onDownload).not.toHaveBeenCalled();
  expect(onLoad).not.toHaveBeenCalled();
});
