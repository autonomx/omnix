import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { RpgWorldBundleTransfer } from './RpgWorldBundleTransfer';

function requestUrl(input: RequestInfo | URL): URL {
  return new URL(typeof input === 'string' ? input : input.toString(), 'http://localhost');
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('RpgWorldBundleTransfer', () => {
  it('downloads an exported world bundle', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      expect(requestUrl(input).pathname).toBe('/api/rpg/worlds/world%3Aportable/export');
      return new Response(new Blob(['portable']), {
        headers: {
          'content-type': 'application/zip',
          'content-disposition': 'attachment; filename="portable.omnix-world.zip"',
        },
      });
    });
    vi.stubGlobal('fetch', fetchMock);
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:portable');
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined);
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);

    render(<RpgWorldBundleTransfer initialWorldId="world:portable" />);
    fireEvent.click(screen.getByRole('button', { name: 'Export world bundle' }));

    expect(await screen.findByText('World bundle exported: portable.omnix-world.zip')).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('imports a bundle under an optional clone world id', async () => {
    const onImported = vi.fn();
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = requestUrl(input);
      expect(url.pathname).toBe('/api/rpg/worlds/import');
      expect(url.searchParams.get('target_world_id')).toBe('world:clone');
      expect(init?.method).toBe('POST');
      expect(init?.body).toBeInstanceOf(File);
      return Response.json({
        ok: true,
        status: 'imported',
        world_id: 'world:clone',
        source_world_id: 'world:source',
        bundle_sha256: 'a'.repeat(64),
        counts: { map_definitions: 2, images_created: 1, images_reused: 1 },
        identifier_map: {},
        warnings: [],
      });
    });
    vi.stubGlobal('fetch', fetchMock);
    render(<RpgWorldBundleTransfer onImported={onImported} />);

    const file = new File(['bundle'], 'source.omnix-world.zip', { type: 'application/zip' });
    fireEvent.change(screen.getByLabelText('World bundle file'), {
      target: { files: [file] },
    });
    fireEvent.change(screen.getByLabelText('New world id (optional)'), {
      target: { value: 'world:clone' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Import world bundle' }));

    expect(await screen.findByText('World imported: world:clone • 2 maps • 2 images')).toBeInTheDocument();
    await waitFor(() => expect(onImported).toHaveBeenCalledWith('world:clone'));
  });
});
