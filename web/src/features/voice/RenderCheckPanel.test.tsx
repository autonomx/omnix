import { MantineProvider } from '@mantine/core';
import { QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { omnixTheme } from '../../design/theme';
import { createTestQueryClient } from '../../test/renderWithProviders';
import { RenderCheckPanel } from './RenderCheckPanel';

function path(input: RequestInfo | URL): string {
  const value = input instanceof Request ? input.url : String(input);
  return new URL(value, 'http://localhost').pathname;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('RenderCheckPanel', () => {
  it('checks a render against its script and lists the worst lines', async () => {
    let request: Record<string, unknown> | undefined;
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (path(input) === '/api/jobs' && init?.method === 'POST') {
        request = JSON.parse(String(init.body)) as Record<string, unknown>;
        return Response.json({ id: 'job:check', module: 'stt', type: 'stt.transcribe', status: 'queued', resource_class: 'gpu:stt', priority: 0, created_at: '', updated_at: '' });
      }
      if (path(input) === '/api/jobs/job%3Acheck') {
        return Response.json({
          id: 'job:check', module: 'stt', type: 'stt.transcribe', status: 'completed', resource_class: 'gpu:stt', priority: 0, created_at: '', updated_at: '',
          output_refs: [{ type: 'render_check', render_check: {
            word_error_rate: 0.25, reference_words: 4,
            lines: [
              { index: 0, speaker: 'Ana', text: 'Hello there.', heard: 'Hello there.', word_error_rate: 0 },
              { index: 1, speaker: 'Ben', text: 'General Kenobi.', heard: 'General Canobi.', word_error_rate: 0.5 },
            ],
          } }],
        });
      }
      return new Response('not found', { status: 404 });
    }));
    render(
      <QueryClientProvider client={createTestQueryClient()}>
        <MantineProvider theme={omnixTheme}><RenderCheckPanel assetId="audio:render" /></MantineProvider>
      </QueryClientProvider>,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Check render' }));
    expect(await screen.findByText('Word error 25.0% over 4 words')).toBeInTheDocument();
    expect(request).toMatchObject({ type: 'stt.transcribe', input_ref: { asset_id: 'audio:render' }, input_payload: { check_render: true } });
    expect(screen.getByText('Line 2 (Ben): 50.0%')).toBeInTheDocument();
    expect(screen.getByText('Heard: General Canobi.')).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByText(/Line 1/)).toBeNull());
  });
});
