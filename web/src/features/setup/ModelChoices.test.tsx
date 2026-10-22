import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { JobRecord } from '../../api/client';
import { renderWithProviders } from '../../test/renderWithProviders';
import { avatarsClient, modelPacksClient, type AvatarLibrary, type ModelPacksStatus, type PackOption, type PackVerdict } from './api/modelPacksClient';
import { ModelPacksPanel } from './ModelPacksPanel';

const GB = 1e9;
const licence = { id: 'Apache-2.0', url: 'https://example.com/licence', commercial_use: true, gated: false };

function option(model: string, label: string, changes: Partial<PackOption> = {}): PackOption {
  return { model, label, default: false, installed: false, model_bytes: 15 * GB, runtime_bytes: 0, status: 'fits',
    reasons: [], note: '', licence, ...changes };
}

function imageBundle(changes: Partial<PackVerdict> = {}): PackVerdict {
  return {
    bundle: 'image-generation', label: 'Image generation', description: 'Text-to-image.', capability: 'image', status: 'fits',
    reasons: [], action: null, models: ['flux2-klein-4b'], runtimes: ['torch', 'image'], installed: false,
    model_bytes: 15 * GB, runtime_bytes: 2.7 * GB, recommended: true, note: '', min_options: 1,
    options: [option('flux2-klein-4b', 'FLUX.2 [klein] 4B', { default: true }), option('z-image-turbo', 'Z-Image Turbo')],
    ...changes,
  };
}

function status(changes: Partial<ModelPacksStatus> = {}): ModelPacksStatus {
  const model = (id: string, label: string, installed = false) => ({ id, label, repo: `org/${id}`, revision: 'a'.repeat(40),
    size_bytes: 15 * GB, installed, disk_bytes: 0, accepted: false, licence: { ...licence, output_terms: '' } });
  return {
    enabled: true, platform: 'windows-x64', packs_folder: 'C:/packs', can_manage: true, can_manage_runtimes: true,
    hardware: { gpus: [{ name: 'NVIDIA GeForce RTX 4090', vram_total_mb: 24564, vram_free_mb: 20000 }] },
    bundles: [imageBundle()],
    runtimes: [],
    models: [model('flux2-klein-4b', 'FLUX.2 [klein] 4B'), model('z-image-turbo', 'Z-Image Turbo')],
    defaults: { voice: { choices: [], current: '' }, image: { choices: [], current: '' } },
    ...changes,
  };
}

beforeEach(() => {
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} });
  vi.spyOn(modelPacksClient, 'selection').mockResolvedValue({ model_bytes: 15 * GB, runtime_bytes: 2.7 * GB, total_bytes: 17.7 * GB });
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('choosing models within a feature', () => {
  it('starts from the defaults, keeps the one a feature needs, and downloads the models chosen', async () => {
    vi.spyOn(modelPacksClient, 'status').mockResolvedValue(status());
    const install = vi.spyOn(modelPacksClient, 'install').mockResolvedValue({ id: 'job-1', status: 'queued' } as unknown as JobRecord);
    vi.spyOn(modelPacksClient, 'job').mockResolvedValue({ id: 'job-1', status: 'queued' } as unknown as JobRecord);
    renderWithProviders(<ModelPacksPanel mode="setup" />);

    const choices = await screen.findByRole('group', { name: 'Image generation choices' });
    const flux = within(choices).getByRole('checkbox', { name: /FLUX\.2 \[klein\] 4B/ });
    expect(flux).toBeChecked();
    expect(flux).toBeDisabled(); // the only one chosen of a feature that needs one
    fireEvent.click(within(choices).getByRole('checkbox', { name: /Z-Image Turbo/ }));
    expect(flux).not.toBeDisabled();
    await waitFor(() => expect(modelPacksClient.selection).toHaveBeenLastCalledWith(
      ['image-generation'], { 'image-generation': ['flux2-klein-4b', 'z-image-turbo'] }));

    fireEvent.click(screen.getByRole('button', { name: 'Review licences and download' }));
    const dialog = await screen.findByRole('dialog');
    for (const box of within(dialog).getAllByRole('checkbox')) fireEvent.click(box);
    fireEvent.click(within(dialog).getByRole('button', { name: 'Accept and download' }));
    await waitFor(() => expect(install).toHaveBeenCalledWith({
      bundle_id: 'image-generation', accept_terms: true, options: ['flux2-klein-4b', 'z-image-turbo'] }));
  });

  it('adds one more model to a downloaded feature after its own licence review', async () => {
    vi.spyOn(modelPacksClient, 'status').mockResolvedValue(status({
      bundles: [imageBundle({ installed: true, options: [option('flux2-klein-4b', 'FLUX.2 [klein] 4B', { default: true, installed: true }),
        option('z-image-turbo', 'Z-Image Turbo')] })],
    }));
    const install = vi.spyOn(modelPacksClient, 'install').mockResolvedValue({ id: 'job-2', status: 'queued' } as unknown as JobRecord);
    vi.spyOn(modelPacksClient, 'job').mockResolvedValue({ id: 'job-2', status: 'queued' } as unknown as JobRecord);
    renderWithProviders(<ModelPacksPanel mode="settings" />);

    const zImage = await screen.findByRole('listitem', { name: 'Z-Image Turbo' });
    // The installed FLUX is the only image model left: it cannot be removed on its own.
    expect(within(screen.getByRole('listitem', { name: 'FLUX.2 [klein] 4B' })).queryByRole('button', { name: 'Remove' })).toBeNull();
    fireEvent.click(within(zImage).getByRole('button', { name: 'Download' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.click(within(dialog).getByRole('checkbox'));
    fireEvent.click(within(dialog).getByRole('button', { name: 'Accept and download' }));
    await waitFor(() => expect(install).toHaveBeenCalledWith({ model_id: 'z-image-turbo', accept_terms: true }));
  });

  it('offers the assistant a Live2D avatar on first run, under its own licences, and applies it after the download', async () => {
    vi.spyOn(modelPacksClient, 'status').mockResolvedValue(status());
    vi.spyOn(modelPacksClient, 'install').mockResolvedValue({ id: 'job-1', status: 'queued' } as unknown as JobRecord);
    vi.spyOn(modelPacksClient, 'job').mockResolvedValue({ id: 'job-1', status: 'queued' } as unknown as JobRecord);
    const shizuku = { id: 'open-llm-vtuber-shizuku', name: 'Shizuku (PRO)', description: 'Classic sample.', installed: false,
      selected: false, preview_path: '/api/character-live2d/models/open-llm-vtuber-shizuku/preview', license_summary: 'Live2D sample data.',
      runtime_license_url: 'https://example.com/runtime', model_license_url: 'https://example.com/model' };
    vi.spyOn(avatarsClient, 'assistantAvatars').mockResolvedValue({ models: [shizuku], runtime_installed: false } as unknown as AvatarLibrary);
    const useForAssistant = vi.spyOn(avatarsClient, 'useForAssistant').mockResolvedValue();
    renderWithProviders(<ModelPacksPanel mode="setup" />);

    const choice = await screen.findByRole('region', { name: 'Assistant avatar' });
    expect(within(choice).getByRole('checkbox', { name: /Assistant avatar: Shizuku/ })).toBeChecked();
    fireEvent.click(screen.getByRole('button', { name: 'Review licences and download' }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByRole('link', { name: 'Live2D Proprietary Software License' })).toHaveAttribute('href', 'https://example.com/runtime');
    const accept = within(dialog).getByRole('button', { name: 'Accept and download' });
    for (const box of within(dialog).getAllByRole('checkbox')) fireEvent.click(box);
    expect(accept).not.toBeDisabled();
    fireEvent.click(accept);
    await waitFor(() => expect(useForAssistant).toHaveBeenCalledWith('open-llm-vtuber-shizuku'));
  });

  it('does not offer an avatar once the assistant has one', async () => {
    vi.spyOn(modelPacksClient, 'status').mockResolvedValue(status());
    vi.spyOn(avatarsClient, 'assistantAvatars').mockResolvedValue({ models: [{ id: 'open-llm-vtuber-shizuku', name: 'Shizuku (PRO)',
      selected: true }], runtime_installed: true } as unknown as AvatarLibrary);
    renderWithProviders(<ModelPacksPanel mode="setup" />);

    await screen.findByRole('button', { name: 'Review licences and download' });
    await waitFor(() => expect(avatarsClient.assistantAvatars).toHaveBeenCalled());
    expect(screen.queryByRole('region', { name: 'Assistant avatar' })).toBeNull();
  });

  it('shows where downloads go and lets the owner choose another folder before downloading', async () => {
    vi.spyOn(modelPacksClient, 'status').mockResolvedValue(status({ packs_folder: 'F:/Omnix/packs' }));
    const choosePacksFolder = vi.fn().mockResolvedValue('E:/Models/OmnixPacks');
    vi.stubGlobal('omnixDesktop', { choosePacksFolder });
    renderWithProviders(<ModelPacksPanel mode="setup" />);

    expect(await screen.findByText('Downloads go to', { exact: false })).toHaveTextContent('Downloads go to F:/Omnix/packs');
    fireEvent.click(screen.getByRole('button', { name: 'Change…' }));
    await waitFor(() => expect(screen.getByText('Downloads go to', { exact: false })).toHaveTextContent('E:/Models/OmnixPacks'));
    expect(choosePacksFolder).toHaveBeenCalledTimes(1);
  });

  it('sets the default voice engine and image model from the downloaded ones', async () => {
    vi.spyOn(modelPacksClient, 'status').mockResolvedValue(status({
      defaults: {
        voice: { choices: [{ model: 'qwen3-tts-0.6b-base', label: 'Qwen3-TTS 0.6B Base' }, { model: 'omnivoice', label: 'OmniVoice' }],
          current: 'qwen3-tts-0.6b-base' },
        image: { choices: [{ model: 'flux2-klein-4b', label: 'FLUX.2 [klein] 4B' }], current: 'flux2-klein-4b' },
      },
    }));
    const setDefaults = vi.spyOn(modelPacksClient, 'setDefaults').mockResolvedValue({
      voice: { choices: [], current: 'omnivoice' }, image: { choices: [], current: 'flux2-klein-4b' } });
    renderWithProviders(<ModelPacksPanel mode="settings" />);

    const voice = await screen.findByRole('combobox', { name: 'Default voice engine' });
    expect(voice).toHaveValue('qwen3-tts-0.6b-base');
    fireEvent.change(voice, { target: { value: 'omnivoice' } });
    await waitFor(() => expect(setDefaults).toHaveBeenCalledWith({ voice: 'omnivoice' }));
    expect(screen.getByRole('combobox', { name: 'Default image model' })).toHaveValue('flux2-klein-4b');
  });
});
