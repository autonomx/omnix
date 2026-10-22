import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { renderWithProviders } from '../../test/renderWithProviders';
import { avatarsClient, type AvatarLibrary } from './api/modelPacksClient';
import { AvatarPacksPanel } from './AvatarPacksPanel';

function library(overrides: Partial<AvatarLibrary> = {}): AvatarLibrary {
  const model = {
    id: 'live2d-sample-haru', name: 'Haru', description: 'Full-featured avatar.', preview_url: 'https://www.live2d.com/haru.jpg',
    preview_path: '/api/character-live2d/previews/live2d-sample-haru', repository: 'Live2D/Cubism Sample Data',
    revision: 'sha256:abc', source_url: 'https://www.live2d.com/sample', model_license_url: 'https://www.live2d.com/terms',
    runtime_license_url: 'https://www.live2d.com/eula', license_summary: 'Live2D sample data.', installed: false, selected: false,
  };
  return { models: [model], runtime_installed: false, can_manage: true, ...overrides };
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('AvatarPacksPanel', () => {
  it('downloads an avatar only after the Live2D terms are accepted, showing its preview through Omnix', async () => {
    vi.spyOn(avatarsClient, 'library').mockResolvedValue(library());
    const install = vi.spyOn(avatarsClient, 'install').mockResolvedValue(
      library({ runtime_installed: true, models: [{ ...library().models[0], installed: true }] }));
    renderWithProviders(<AvatarPacksPanel />);

    const haru = await screen.findByRole('listitem', { name: 'Haru' });
    expect(haru.querySelector('img')?.getAttribute('src')).toBe('/api/character-live2d/previews/live2d-sample-haru');
    const download = within(haru).getByRole('button', { name: 'Download' });
    expect(download).toBeDisabled();
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(download);
    await waitFor(() => expect(install).toHaveBeenCalledWith('live2d-sample-haru'));
    expect(await within(haru).findByText('Downloaded')).toBeInTheDocument();
  });

  it('removes a downloaded avatar, and shows why when a character still uses it', async () => {
    vi.spyOn(avatarsClient, 'library').mockResolvedValue(library({ models: [{ ...library().models[0], installed: true }] }));
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.spyOn(avatarsClient, 'remove').mockRejectedValue(new Error('Haru is the avatar of Maya; choose another avatar for them first'));
    renderWithProviders(<AvatarPacksPanel />);

    fireEvent.click(await screen.findByRole('button', { name: 'Remove' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('avatar of Maya');
  });

  it('shows a member the avatars without download or remove controls', async () => {
    vi.spyOn(avatarsClient, 'library').mockResolvedValue(library({ can_manage: false }));
    renderWithProviders(<AvatarPacksPanel />);

    expect(await screen.findByRole('listitem', { name: 'Haru' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Download' })).toBeNull();
    expect(screen.getByText(/owner or an admin downloads and removes avatars/)).toBeInTheDocument();
  });
});
