import { MantineProvider } from '@mantine/core';
import { QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { omnixModules } from '../../app/modules';
import { omnixTheme } from '../../design/theme';
import { VoiceCloningWorkspace } from './VoiceCloningWorkspace';
import { createTestQueryClient } from '../../test/renderWithProviders';

function renderVoiceCloning() {
  const queryClient = createTestQueryClient();
  const module = omnixModules.find((entry) => entry.id === 'voice-cloning');
  if (!module) throw new Error('Voice Cloning module is missing');
  return render(
    <MantineProvider theme={omnixTheme} defaultColorScheme="dark">
      <QueryClientProvider client={queryClient}>
        <VoiceCloningWorkspace module={module} />
      </QueryClientProvider>
    </MantineProvider>,
  );
}

function requestPath(input: RequestInfo | URL): string {
  return typeof input === 'string' ? new URL(input, 'http://localhost').pathname : new URL(input.toString()).pathname;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('VoiceCloningWorkspace', () => {
  it('clones through the same working job as Voice Studio, with central defaults', async () => {
    let request: Record<string, unknown> | undefined;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      if (path === '/api/settings/profile') {
        return Response.json({ success: true, settings: { settings_control_center: {
          revision: 'voice-defaults-r1',
          global: { providers: { voiceCloning: 'qwen-voice' } },
          voice: { cloningLanguage: 'French', cloningQuality: 'Standard' },
        } } });
      }
      if (path === '/api/jobs' && init?.method === 'POST') {
        request = JSON.parse(String(init.body)) as Record<string, unknown>;
        return Response.json({ id: 'job:clone', module: 'voice-cloning', type: 'voice-cloning.create-profile', status: 'queued', resource_class: 'gpu:tts', created_at: '2026-06-14T00:00:00Z', updated_at: '2026-06-14T00:00:00Z', priority: 0 });
      }
      if (path === '/api/jobs') return Response.json({ jobs: [] });
      if (path === '/api/assets') {
        return Response.json({ assets: [{ id: 'voice-cloning:narrator', module: 'voice-cloning', type: 'voice_profile', mime_type: 'audio/wav', file_name: 'narrator.wav', metadata: { profile_name: 'Narrator' }, created_at: '2026-06-14T00:00:00Z' }] });
      }
      return new Response('not found', { status: 404 });
    });
    vi.stubGlobal('fetch', fetchMock);

    renderVoiceCloning();
    expect(await screen.findByRole('region', { name: 'Clone a Voice' })).toBeInTheDocument();
    expect(await screen.findByText('Narrator')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByLabelText('Language / Accent')).toHaveValue('French'));
    expect(screen.getByLabelText('Quality')).toHaveValue('Standard');
    // Preview and Use belong to Voice Studio, which has the engine and the script.
    expect(screen.queryByRole('button', { name: 'Use' })).toBeNull();

    fireEvent.change(screen.getByLabelText('Voice Name'), { target: { value: 'Maya' } });
    fireEvent.change(screen.getByLabelText(/Audio sample/), { target: { files: [new File(['voice sample'], 'maya.wav', { type: 'audio/wav' })] } });
    await waitFor(() => expect(screen.getByRole('button', { name: 'Create Clone' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: 'Create Clone' }));
    await waitFor(() => expect(request).toBeDefined());
    expect(request?.type).toBe('voice-cloning.create-profile');
    expect((request?.input_payload as Record<string, unknown>).provider_id).toBe('qwen-voice');
    expect((request?.input_payload as Record<string, unknown>).language).toBe('French');
  });
});
