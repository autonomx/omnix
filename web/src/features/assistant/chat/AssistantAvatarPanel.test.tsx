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
    expect(screen.queryByRole('tab', { name: 'Generated avatar' })).toBeNull();
    expect(screen.queryByText('Use your own image')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Download and use Live2D avatar' }));
    await waitFor(() => expect(requests).toContain('POST /api/characters/system-assistant/live2d-avatar'));
    expect(requests).toContain('GET /api/characters/system-assistant/live2d-models');
  });
});
