import { QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AssistantAvatarPanel } from './AssistantAvatarPanel';
import { createTestQueryClient } from '../../../test/renderWithProviders';

vi.mock('./Live2DModelThumbnail', () => ({
  Live2DModelThumbnail: ({ model }: { model: { name: string } }) => <span>{model.name} preview</span>,
}));

const shizuku = {
  id: 'open-llm-vtuber-shizuku', name: 'Shizuku (PRO)', description: 'Classic expressive model.', preview_url: 'unused',
  repository: 'Open-LLM-VTuber/Open-LLM-VTuber', revision: 'revision', source_url: 'https://example.com/source',
  model_license_url: 'https://example.com/model-license', runtime_license_url: 'https://example.com/runtime-license',
  license_summary: 'Sample terms apply.', installed: false, selected: false,
};

afterEach(() => vi.unstubAllGlobals());

describe('AssistantAvatarPanel', () => {
  it('chooses a Live2D avatar for the System Assistant, with no generated-avatar tools', async () => {
    const requests: string[] = [];
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const request = input instanceof Request ? input : new Request(new URL(input.toString(), 'http://localhost'), init);
      const url = new URL(request.url);
      requests.push(`${request.method} ${url.pathname}`);
      if (url.pathname.endsWith('/avatar-pack/optional')) return Response.json(null);
      if (url.pathname.endsWith('/live2d-models')) return Response.json({ models: [shizuku], runtime_installed: false });
      if (url.pathname.endsWith('/live2d-avatar')) {
        return Response.json({ ok: true, character_id: 'system-assistant', downloaded: true, avatar_pack: {
          character_id: 'system-assistant', version: 1, render_mode: 'viseme', renderer: 'live2d', rig_asset_id: 'live2d-model:shizuku',
          mouth_frames: {}, blink_frames: {}, expression_frames: {}, outfit_frames: {}, background_asset_ids: {}, mouth_anchor: {},
          created_at: '2026-10-22T00:00:00Z', updated_at: '2026-10-22T00:00:00Z' } });
      }
      return new Response('not found', { status: 404 });
    }));
    render(<QueryClientProvider client={createTestQueryClient()}><AssistantAvatarPanel /></QueryClientProvider>);

    fireEvent.click(await screen.findByRole('button', { name: /Shizuku \(PRO\)/ }));
    expect(screen.getAllByRole('tab').map((tab) => tab.textContent)).toEqual(['Live2D avatar', 'Live portrait']);
    expect(screen.queryByText('Use your own image')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Download and use Live2D avatar' }));
    await waitFor(() => expect(requests).toContain('POST /api/characters/system-assistant/live2d-avatar'));
    expect(requests).toContain('GET /api/characters/system-assistant/live2d-models');
  });

  it('saves a live portrait for the System Assistant and can turn it off', async () => {
    const requests: string[] = [];
    let stored: Record<string, unknown> | null = null;
    let savedBody: Record<string, unknown> | null = null;
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const request = input instanceof Request ? input : new Request(new URL(input.toString(), 'http://localhost'), init);
      const url = new URL(request.url);
      requests.push(`${request.method} ${url.pathname}`);
      if (url.pathname.endsWith('/avatar-pack/optional')) return Response.json(stored);
      if (url.pathname.endsWith('/live2d-models')) return Response.json({ models: [shizuku], runtime_installed: false });
      if (url.pathname === '/api/image-generation/references') return Response.json({ asset: { id: 'image:face' } });
      if (url.pathname.endsWith('/avatar-pack') && request.method === 'PUT') {
        savedBody = await request.json() as Record<string, unknown>;
        stored = {
          character_id: 'system-assistant', version: 1, render_mode: 'static', renderer: 'portrait', base_asset_id: 'image:face',
          fallback_renderer: 'sprite', portrait_emotion: 'character', mouth_frames: {}, blink_frames: {}, expression_frames: {},
          outfit_frames: {}, background_asset_ids: {}, mouth_anchor: {},
          created_at: '2026-11-04T00:00:00Z', updated_at: '2026-11-04T00:00:00Z',
        };
        return Response.json(stored);
      }
      if (url.pathname.endsWith('/avatar-pack') && request.method === 'DELETE') {
        stored = null;
        return Response.json({ character_id: 'system-assistant', deleted: true });
      }
      return new Response('not found', { status: 404 });
    }));
    render(<QueryClientProvider client={createTestQueryClient()}><AssistantAvatarPanel /></QueryClientProvider>);

    fireEvent.click(await screen.findByRole('tab', { name: 'Live portrait' }));
    expect(screen.getByRole('option', { name: "System Assistant's speaking style" })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Turn off the portrait' })).toBeNull();
    fireEvent.change(screen.getByLabelText('Portrait image'), { target: { files: [new File(['face'], 'face.png', { type: 'image/png' })] } });
    fireEvent.click(screen.getByRole('button', { name: 'Use this portrait' }));

    await waitFor(() => expect(requests).toContain('PUT /api/characters/system-assistant/avatar-pack'));
    expect(savedBody).toMatchObject({ renderer: 'portrait', base_asset_id: 'image:face', fallback_renderer: 'sprite', rig_asset_id: null });
    expect(await screen.findByText(/Live calls with System Assistant now show it/)).toBeInTheDocument();

    fireEvent.click(await screen.findByRole('button', { name: 'Turn off the portrait' }));
    await waitFor(() => expect(requests).toContain('DELETE /api/characters/system-assistant/avatar-pack'));
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Turn off the portrait' })).toBeNull());
  });

  it('opens on the live portrait when that is the avatar in use', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const request = input instanceof Request ? input : new Request(new URL(input.toString(), 'http://localhost'), init);
      const url = new URL(request.url);
      if (url.pathname.endsWith('/avatar-pack/optional')) {
        return Response.json({
          character_id: 'system-assistant', version: 2, render_mode: 'static', renderer: 'portrait', base_asset_id: 'image:face',
          fallback_renderer: 'orb', portrait_emotion: 'happy', mouth_frames: {}, blink_frames: {}, expression_frames: {},
          outfit_frames: {}, background_asset_ids: {}, mouth_anchor: {},
          created_at: '2026-11-04T00:00:00Z', updated_at: '2026-11-04T00:00:00Z',
        });
      }
      if (url.pathname.endsWith('/live2d-models')) return Response.json({ models: [shizuku], runtime_installed: false });
      return new Response('not found', { status: 404 });
    }));
    render(<QueryClientProvider client={createTestQueryClient()}><AssistantAvatarPanel /></QueryClientProvider>);

    expect(await screen.findByRole('button', { name: 'Save the portrait' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Live portrait' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('button', { name: 'Turn off the portrait' })).toBeInTheDocument();
  });
});
