import { MantineProvider } from '@mantine/core';
import { QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { omnixTheme } from '../../../design/theme';
import { createTestQueryClient } from '../../../test/renderWithProviders';
import { OwnerAbilitiesPanel } from './OwnerAbilitiesPanel';

type Call = { method: string; path: string; body: unknown };

function serve(granted: boolean, { failFirstRead = false } = {}) {
  const calls: Call[] = [];
  let reads = 0;
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const request = input instanceof Request ? input : null;
    const url = new URL(request ? request.url : input.toString(), 'http://localhost');
    const method = request?.method ?? init?.method ?? 'GET';
    const text = request ? await request.clone().text() : String(init?.body ?? '');
    const body = text ? JSON.parse(text) as { granted?: boolean } : null;
    calls.push({ method, path: decodeURIComponent(url.pathname), body });
    if (method === 'GET' && failFirstRead && reads++ === 0) return Response.json({ detail: 'down' }, { status: 503 });
    const now = method === 'PUT' ? Boolean(body?.granted) : granted;
    return Response.json({
      owner_id: 'jinx',
      abilities: [{ id: 'web_search', label: 'Look things up on the web', kind: 'lookup', granted: now }],
    });
  }));
  return calls;
}

function renderPanel() {
  return render(
    <MantineProvider theme={omnixTheme} defaultColorScheme="dark">
      <QueryClientProvider client={createTestQueryClient()}>
        <OwnerAbilitiesPanel ownerId="jinx" ownerName="Jinx" />
      </QueryClientProvider>
    </MantineProvider>,
  );
}

afterEach(() => vi.unstubAllGlobals());

describe('OwnerAbilitiesPanel', () => {
  it('shows each ability with its grant and saves a change', async () => {
    const calls = serve(false);
    renderPanel();

    const box = await screen.findByRole('checkbox', { name: /look things up on the web/i });
    expect(box).not.toBeChecked();
    expect(screen.getByText('What Jinx can do in calls')).toBeInTheDocument();
    fireEvent.click(box);

    await waitFor(() => expect(box).toBeChecked());
    expect(calls.find((call) => call.method === 'PUT')).toEqual({
      method: 'PUT', path: '/api/assistant/tools/abilities/jinx/web_search', body: { granted: true },
    });
  });

  it('offers to try again when the grants cannot be loaded', async () => {
    serve(true, { failFirstRead: true });
    renderPanel();

    fireEvent.click(await screen.findByRole('button', { name: 'Try again' }));

    expect(await screen.findByRole('checkbox', { name: /look things up on the web/i })).toBeChecked();
  });
});
