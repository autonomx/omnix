import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { JobRecord } from '../../api/client';
import { renderWithProviders } from '../../test/renderWithProviders';
import { modelPacksClient, type ModelPacksStatus } from './api/modelPacksClient';
import { CapabilityNotice } from './CapabilityNotice';
import { ModelPacksPanel } from './ModelPacksPanel';

const GB = 1e9;

function status(overrides: Partial<ModelPacksStatus> = {}): ModelPacksStatus {
  return {
    enabled: true,
    platform: 'windows-x64',
    packs_folder: 'C:/Users/me/AppData/Local/OmnixDesktop/packs',
    can_manage: true,
    can_manage_runtimes: true,
    hardware: {
      gpus: [{ name: 'NVIDIA GeForce RTX 4080', vram_total_mb: 16376, vram_free_mb: 15000 }],
      nvidia_driver: '560.94', memory: { total_bytes: 64 * 2 ** 30 }, disk: { free_bytes: 400 * GB },
    },
    bundles: [
      { bundle: 'voice-input', label: 'Voice input', description: 'Live voice in chat.', capability: 'live_stt',
        status: 'fits', reasons: [], action: null, models: ['nemotron', 'eou'], runtimes: ['torch', 'stt'],
        installed: false, model_bytes: 2.9 * GB, runtime_bytes: 2.8 * GB, recommended: true, note: '' },
      { bundle: 'image-generation', label: 'Image generation', description: 'Text-to-image.', capability: 'image',
        status: 'unavailable', reasons: ['Needs an NVIDIA GPU (found AMD Radeon RX 7900 XTX).'], action: null,
        models: ['flux'], runtimes: ['torch', 'image'], installed: false, model_bytes: 16 * GB, runtime_bytes: 0.2 * GB,
        recommended: false, note: '' },
    ],
    runtimes: [
      { id: 'torch', label: 'GPU runtime', kind: 'torch-layer', platform: 'windows-x64', accelerator: 'cuda', base: '',
        licences: ['BSD-3-Clause (PyTorch)'], requires: {}, installed: false, current: false, installed_at: '', download_bytes: 2.5 * GB },
      { id: 'stt', label: 'Speech runtime', kind: 'overlay', platform: 'windows-x64', accelerator: 'cuda', base: 'torch',
        licences: ['Apache-2.0 (NeMo)'], requires: {}, installed: false, current: false, installed_at: '', download_bytes: 0.3 * GB },
    ],
    models: [
      { id: 'nemotron', label: 'Nemotron streaming 0.6B', repo: 'nvidia/n', revision: 'a'.repeat(40), size_bytes: 2.5 * GB,
        installed: false, disk_bytes: 0, accepted: false,
        licence: { id: 'NVIDIA Open Model License', url: 'https://example.com/nvidia', commercial_use: true, gated: false, output_terms: '' } },
      { id: 'eou', label: 'Parakeet realtime EOU', repo: 'nvidia/e', revision: 'b'.repeat(40), size_bytes: 0.4 * GB,
        installed: false, disk_bytes: 0, accepted: false,
        licence: { id: 'NVIDIA Open Model License', url: 'https://example.com/nvidia', commercial_use: true, gated: false, output_terms: '' } },
    ],
    ...overrides,
  };
}

function job(id: string, jobStatus: string, progress?: { current: number; total: number; message: string }): JobRecord {
  return { id, type: 'models.install', status: jobStatus, progress } as unknown as JobRecord;
}

beforeEach(() => {
  // Mantine's segmented control measures itself.
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} });
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  delete window.omnixDesktop;
});

describe('ModelPacksPanel', () => {
  it('preselects what fits this computer and shows why the rest cannot run', async () => {
    vi.spyOn(modelPacksClient, 'status').mockResolvedValue(status());
    vi.spyOn(modelPacksClient, 'selection').mockResolvedValue({ model_bytes: 2.9 * GB, runtime_bytes: 2.8 * GB, total_bytes: 5.7 * GB });
    renderWithProviders(<ModelPacksPanel mode="setup" />);

    const voice = await screen.findByRole('listitem', { name: 'Voice input' });
    expect(within(voice).getByRole('checkbox')).toBeChecked();
    expect(within(voice).getByText('✓ Fits')).toBeInTheDocument();
    const image = screen.getByRole('listitem', { name: 'Image generation' });
    expect(within(image).getByRole('checkbox')).toBeDisabled();
    expect(within(image).getByText('Needs an NVIDIA GPU (found AMD Radeon RX 7900 XTX).')).toBeInTheDocument();
    expect(await screen.findByText(/Download: 5\.7 GB/)).toBeInTheDocument();
    // Each bundle names its models, with size and licence, and says the GPU runtime downloads once.
    const listed = within(voice).getByRole('list', { name: 'Voice input models' });
    expect(within(listed).getAllByRole('listitem').map((item) => item.textContent)).toEqual([
      'Nemotron streaming 0.6B · 2.5 GB · NVIDIA Open Model License',
      'Parakeet realtime EOU · 0.4 GB · NVIDIA Open Model License',
    ]);
    expect(within(voice).getByText(/2\.5 GB of it is the shared GPU runtime, downloaded once/)).toBeInTheDocument();
    expect(screen.getByText(/NVIDIA GeForce RTX 4080 · 16 GB VRAM · driver 560\.94/)).toBeInTheDocument();
  });

  it('shows a member what this computer runs, without the download and remove controls', async () => {
    vi.spyOn(modelPacksClient, 'status').mockResolvedValue(status({
      can_manage: false, can_manage_runtimes: false,
      bundles: [{ ...status().bundles[0], installed: true }, status().bundles[1]],
    }));
    renderWithProviders(<ModelPacksPanel mode="setup" />);

    const voice = await screen.findByRole('listitem', { name: 'Voice input' });
    expect(within(voice).getByRole('checkbox')).toBeDisabled();
    expect(within(voice).queryByRole('button', { name: 'Remove' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Review licences and download' })).toBeNull();
    expect(screen.getByText(/owner or an admin downloads and removes models/)).toBeInTheDocument();
  });

  it('installs only after every licence is accepted, and shows the download progress', async () => {
    vi.spyOn(modelPacksClient, 'status').mockResolvedValue(status());
    vi.spyOn(modelPacksClient, 'selection').mockResolvedValue({ model_bytes: 2.9 * GB, runtime_bytes: 2.8 * GB, total_bytes: 5.7 * GB });
    const install = vi.spyOn(modelPacksClient, 'install').mockResolvedValue(job('job-1', 'queued'));
    vi.spyOn(modelPacksClient, 'job').mockResolvedValue(job('job-1', 'running', { current: 1, total: 4, message: 'Downloading GPU runtime' }));
    renderWithProviders(<ModelPacksPanel mode="setup" />);

    fireEvent.click(await screen.findByRole('button', { name: 'Review licences and download' }));
    const dialog = await screen.findByRole('dialog', { name: 'Review the licences' });
    const confirm = within(dialog).getByRole('button', { name: 'Accept and download' });
    expect(confirm).toBeDisabled();
    for (const checkbox of within(dialog).getAllByRole('checkbox')) fireEvent.click(checkbox);
    expect(confirm).toBeEnabled();
    expect(within(dialog).getByText(/GPU runtime \(BSD-3-Clause \(PyTorch\)\)/)).toBeInTheDocument();
    fireEvent.click(confirm);

    await waitFor(() => expect(install).toHaveBeenCalledWith({ bundle_id: 'voice-input', accept_terms: true }));
    expect(await screen.findByText(/Downloading GPU runtime · 25%/)).toBeInTheDocument();
  });

  it('shows the refusal reason the server gives', async () => {
    const { ApiError } = await import('../../api/errors');
    vi.spyOn(modelPacksClient, 'status').mockResolvedValue(status());
    vi.spyOn(modelPacksClient, 'selection').mockResolvedValue({ model_bytes: 0, runtime_bytes: 0, total_bytes: 0 });
    vi.spyOn(modelPacksClient, 'install').mockRejectedValue(
      new ApiError(403, JSON.stringify({ detail: 'only the workspace owner can install GPU runtime; ask them to do it' })));
    renderWithProviders(<ModelPacksPanel mode="setup" />);
    fireEvent.click(await screen.findByRole('button', { name: 'Review licences and download' }));
    const dialog = await screen.findByRole('dialog', { name: 'Review the licences' });
    for (const checkbox of within(dialog).getAllByRole('checkbox')) fireEvent.click(checkbox);
    fireEvent.click(within(dialog).getByRole('button', { name: 'Accept and download' }));
    expect(await screen.findByText('only the workspace owner can install GPU runtime; ask them to do it')).toBeInTheDocument();
  });

  it('says where models come from outside the desktop app, and stays out of Settings there', async () => {
    vi.spyOn(modelPacksClient, 'status').mockResolvedValue({ enabled: false } as ModelPacksStatus);
    const { unmount } = renderWithProviders(<ModelPacksPanel mode="setup" />);
    expect(await screen.findByText(/part of the Omnix desktop app/)).toBeInTheDocument();
    unmount();
    const { container } = renderWithProviders(<ModelPacksPanel mode="settings" />);
    await waitFor(() => expect(modelPacksClient.status).toHaveBeenCalledTimes(2));
    expect(container.querySelector('.setup-panel')).toBeNull();
  });
});

describe('CapabilityNotice', () => {
  it('offers the download where a desktop capability is missing', async () => {
    vi.spyOn(modelPacksClient, 'capabilities').mockResolvedValue({
      desktop: true,
      capabilities: { live_stt: { bundle: 'voice-input', label: 'Voice input', installed: false, running: false } },
    });
    renderWithProviders(<CapabilityNotice capability="live_stt" purpose="Live voice" />);
    expect(await screen.findByRole('link', { name: 'Download Voice input' })).toHaveAttribute('href', '/setup');
  });

  it('renders nothing outside the desktop app or once installed', async () => {
    const capabilities = vi.spyOn(modelPacksClient, 'capabilities').mockResolvedValue({
      desktop: false, capabilities: { live_stt: { bundle: 'voice-input', label: 'Voice input', installed: true, running: false } },
    });
    const { container } = renderWithProviders(<CapabilityNotice capability="live_stt" purpose="Live voice" />);
    await waitFor(() => expect(capabilities).toHaveBeenCalled());
    expect(container.querySelector('.setup-capability-notice')).toBeNull();
  });
});
