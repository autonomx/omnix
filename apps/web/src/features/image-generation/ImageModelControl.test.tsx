import { MantineProvider } from '@mantine/core';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { omnixTheme } from '../../design/theme';
import {
  ImageModelControl,
  imageModelGenerationBlockReason,
  type ImageModelStatusPayload,
} from './ImageModelControl';

const unloadedStatus: ImageModelStatusPayload = {
  ok: true,
  service: 'image',
  enabled: true,
  provider: 'flux_klein',
  model: 'FLUX.2 [klein] 4B',
  loaded: false,
  state: 'unloaded',
  warmed_up: false,
  warmup_state: 'not_started',
  explicit_load_required: true,
  local_model: {
    ok: true,
    exists: true,
    complete: true,
    missing: [],
    local_dir: 'resources/models/image/flux2-klein-4b',
  },
};

function renderControl(status: ImageModelStatusPayload, overrides: Partial<React.ComponentProps<typeof ImageModelControl>> = {}) {
  const props = {
    status,
    statusLoading: false,
    action: null,
    onLoad: vi.fn(),
    onUnload: vi.fn(),
    onRefresh: vi.fn(),
    ...overrides,
  } as React.ComponentProps<typeof ImageModelControl>;
  render(
    <MantineProvider theme={omnixTheme} defaultColorScheme="dark">
      <ImageModelControl {...props} />
    </MantineProvider>,
  );
  return props;
}

describe('ImageModelControl', () => {
  it('loads and warms an unloaded FLUX model on demand', () => {
    const props = renderControl(unloadedStatus);
    fireEvent.click(screen.getByRole('button', { name: 'Load & Warm Model' }));
    expect(props.onLoad).toHaveBeenCalledTimes(1);
    expect(screen.getByText('unloaded')).toBeInTheDocument();
    expect(screen.getByText('resources/models/image/flux2-klein-4b')).toBeInTheDocument();
  });

  it('reports a warmed resident model as ready', () => {
    renderControl({
      ...unloadedStatus,
      loaded: true,
      state: 'loaded',
      warmed_up: true,
      warmup_state: 'completed',
    });
    expect(screen.getByText(/resident and warmed/i)).toBeInTheDocument();
  });

  it('blocks actions while the resident model is warming', () => {
    renderControl({ ...unloadedStatus, loaded: true, state: 'warming' });
    expect(screen.getByText('warming')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Unload Model' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Refresh Status' })).toBeDisabled();
  });

  it('unloads a resident model and exposes refresh', () => {
    const props = renderControl({ ...unloadedStatus, loaded: true, state: 'loaded' });
    fireEvent.click(screen.getByRole('button', { name: 'Unload Model' }));
    fireEvent.click(screen.getByRole('button', { name: 'Refresh Status' }));
    expect(props.onUnload).toHaveBeenCalledTimes(1);
    expect(props.onRefresh).toHaveBeenCalledTimes(1);
  });

  it('blocks loading when local weights are incomplete', () => {
    renderControl({
      ...unloadedStatus,
      ok: false,
      local_model: {
        exists: true,
        complete: false,
        missing: ['scheduler/scheduler_config.json'],
        local_dir: 'resources/models/image/flux2-klein-4b',
      },
    });
    expect(screen.getByRole('button', { name: 'Load & Warm Model' })).toBeDisabled();
    expect(screen.getByRole('alert')).toHaveTextContent('scheduler/scheduler_config.json');
  });
});

describe('imageModelGenerationBlockReason', () => {
  it('requires an explicitly loaded and non-warming FLUX model', () => {
    expect(imageModelGenerationBlockReason(unloadedStatus, false, false)).toContain('Load and warm FLUX.2');
    expect(imageModelGenerationBlockReason({ ...unloadedStatus, loaded: true, state: 'warming' }, false, false)).toContain('warming up');
    expect(imageModelGenerationBlockReason({ ...unloadedStatus, loaded: true, state: 'loaded' }, false, false)).toBeUndefined();
    expect(imageModelGenerationBlockReason(undefined, false, true)).toContain('service is unavailable');
  });
});
