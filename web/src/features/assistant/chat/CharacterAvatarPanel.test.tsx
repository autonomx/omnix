import { QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { CharacterAvatarPanel } from './CharacterAvatarPanel';
import { createTestQueryClient } from '../../../test/renderWithProviders';

vi.mock('./Live2DModelThumbnail', () => ({
  Live2DModelThumbnail: ({ model }: { model: { name: string } }) => <span aria-label={`${model.name} rig preview`}>{model.name} preview</span>,
}));

const character = {
  id: 'maya',
  display_name: 'Maya',
} as never;

const models = [
  {
    id: 'open-llm-vtuber-mao-pro',
    name: 'Niziiro Mao (PRO)',
    description: 'Expressive front-facing model.',
    preview_url: 'unused',
    repository: 'Open-LLM-VTuber/Open-LLM-VTuber',
    revision: 'revision',
    source_url: 'https://example.com/source',
    model_license_url: 'https://example.com/model-license',
    runtime_license_url: 'https://example.com/runtime-license',
    license_summary: 'Sample terms apply.',
    installed: false,
    selected: false,
  },
  {
    id: 'open-llm-vtuber-shizuku',
    name: 'Shizuku (PRO)',
    description: 'Classic expressive model.',
    preview_url: 'unused',
    repository: 'Open-LLM-VTuber/Open-LLM-VTuber',
    revision: 'revision',
    source_url: 'https://example.com/source',
    model_license_url: 'https://example.com/model-license',
    runtime_license_url: 'https://example.com/runtime-license',
    license_summary: 'Sample terms apply.',
    installed: true,
    selected: true,
  },
];

function renderPanel() {
  const queryClient = createTestQueryClient();
  return render(<QueryClientProvider client={queryClient}><CharacterAvatarPanel character={character} /></QueryClientProvider>);
}

afterEach(() => vi.unstubAllGlobals());

describe('CharacterAvatarPanel', () => {
  it('uses the active rig for both the main preview and its selector card', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(input.toString(), 'http://localhost');
      if (url.pathname.endsWith('/avatar-pack/optional')) {
        return Response.json({
          character_id: 'maya',
          version: 4,
          render_mode: 'viseme',
          renderer: 'live2d',
          rig_asset_id: 'character-live2d:open-llm-vtuber-shizuku',
          base_asset_id: null,
          mouth_frames: {},
          blink_frames: {},
          expression_frames: {},
          outfit_frames: {},
          background_asset_ids: {},
          mouth_anchor: { x: 0.5, y: 0.68 },
          created_at: '2026-08-01T00:00:00Z',
          updated_at: '2026-08-01T00:00:00Z',
        });
      }
      if (url.pathname.endsWith('/live2d-models')) {
        return Response.json({ models, runtime_installed: true });
      }
      return new Response('not found', { status: 404 });
    }));

    renderPanel();

    expect(await screen.findByRole('region', { name: 'Live2D avatar catalog' })).toBeInTheDocument();
    await waitFor(() => expect(screen.getAllByLabelText('Shizuku (PRO) rig preview')).toHaveLength(2));
  });

  it('allows switching models again after one has been downloaded and activated', async () => {
    let activeModelId = 'open-llm-vtuber-shizuku';
    let maoInstalled = false;
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(input.toString(), 'http://localhost');
      if (url.pathname.endsWith('/avatar-pack/optional')) return Response.json(null);
      if (url.pathname.endsWith('/live2d-models')) {
        return Response.json({
          models: models.map((model) => ({
            ...model,
            installed: model.id === 'open-llm-vtuber-mao-pro' ? maoInstalled : model.installed,
            selected: model.id === activeModelId,
          })),
          runtime_installed: true,
        });
      }
      if (url.pathname.endsWith('/live2d-avatar')) {
        activeModelId = 'open-llm-vtuber-mao-pro';
        maoInstalled = true;
        return Response.json({ ok: true, character_id: 'maya', avatar_pack: null, downloaded: true });
      }
      return new Response('not found', { status: 404 });
    }));

    renderPanel();
    fireEvent.click(await screen.findByRole('tab', { name: 'Live2D avatar' }));
    fireEvent.click(await screen.findByRole('button', { name: /Niziiro Mao \(PRO\)/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Download and use Live2D avatar' }));

    await waitFor(() => expect(screen.getByRole('button', { name: 'Live2D avatar active' })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /Shizuku \(PRO\).*Installed/ }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Use this Live2D avatar' })).toBeInTheDocument());
  });
});

describe('the live portrait tab', () => {
  const portraitPack = {
    character_id: 'maya', version: 2, render_mode: 'static', renderer: 'portrait', rig_asset_id: 'rig:maya',
    base_asset_id: 'image:maya-face', mouth_frames: {}, blink_frames: {}, expression_frames: {}, outfit_frames: {},
    background_asset_ids: {}, mouth_anchor: {}, fallback_renderer: 'sprite', portrait_emotion: 'character',
    created_at: '2026-10-30T00:00:00Z', updated_at: '2026-10-30T00:00:00Z',
  };

  function stubGateway(preview: Record<string, unknown>) {
    const calls: { path: string; body: unknown }[] = [];
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(input.toString(), 'http://localhost');
      const body = typeof init?.body === 'string' ? JSON.parse(init.body) as unknown : null;
      calls.push({ path: url.pathname, body });
      if (url.pathname.endsWith('/avatar-pack/optional')) return Response.json(portraitPack);
      if (url.pathname.endsWith('/live2d-models')) return Response.json({ models: [], runtime_installed: false });
      if (url.pathname.endsWith('/portrait-preview')) return Response.json(preview);
      if (url.pathname.endsWith('/avatar-pack') && init?.method === 'PUT') {
        return Response.json({ ...portraitPack, ...(body as object), version: 3 });
      }
      if (url.pathname.endsWith('/model-packs/capabilities')) return Response.json({ desktop: false, capabilities: {} });
      return new Response('not found', { status: 404 });
    }));
    return calls;
  }

  it('opens on a portrait pack, explains a refused preview and saves the chosen emotion and fallback', async () => {
    const calls = stubGateway({ ok: false, code: 'no_face', message: '', sample_rate: 0, audio: '', fps: 25, frames: [] });
    renderPanel();
    expect(await screen.findByRole('tab', { name: 'Live portrait', selected: true })).toBeTruthy();
    expect(screen.getByAltText('Maya portrait').getAttribute('src')).toBe('/api/assets/image%3Amaya-face/file');

    fireEvent.click(screen.getByRole('button', { name: 'Preview' }));
    expect(await screen.findByText(/No face was found in this image/)).toBeTruthy();
    expect(calls.find((call) => call.path.endsWith('/portrait-preview'))?.body).toMatchObject({
      asset_id: 'image:maya-face', emotion: 'neutral',
    });

    fireEvent.change(screen.getByLabelText('Portrait emotion'), { target: { value: 'happy' } });
    fireEvent.change(screen.getByLabelText('Portrait fallback'), { target: { value: 'live2d' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save the portrait' }));
    await waitFor(() => expect(screen.getByText(/The live portrait is saved/)).toBeTruthy());
    expect(calls.find((call) => call.path.endsWith('/avatar-pack') && call.body)?.body).toMatchObject({
      expected_version: 2, renderer: 'portrait', base_asset_id: 'image:maya-face', fallback_renderer: 'live2d',
      rig_asset_id: 'rig:maya', portrait_emotion: 'happy',
    });
  });
});
