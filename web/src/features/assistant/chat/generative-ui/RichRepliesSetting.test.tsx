import { QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { createTestQueryClient } from '../../../../test/renderWithProviders';
import { RichRepliesSetting } from './RichRepliesSetting';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function renderSetting(sessionId: string | null, value: 'on' | 'off' | null | undefined) {
  return render(
    <QueryClientProvider client={createTestQueryClient()}>
      <RichRepliesSetting sessionId={sessionId} value={value} />
    </QueryClientProvider>,
  );
}

describe('RichRepliesSetting', () => {
  it('writes the choice to the current session', async () => {
    const fetchMock = vi.fn(async () => Response.json({ ok: true, session_id: 'chat:1', rich_replies: 'on' }));
    vi.stubGlobal('fetch', fetchMock);
    renderSetting('chat:1', null);

    const select = screen.getByRole('combobox', { name: 'Rich replies in this chat' });
    expect(select).toHaveValue('default');
    fireEvent.change(select, { target: { value: 'on' } });

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(String(url)).toContain('/api/chat/sessions/chat%3A1/rich-replies');
    expect(JSON.parse(String(init.body))).toEqual({ rich_replies: 'on' });
  });

  it('sends null to return to the default and is disabled without a session', async () => {
    const fetchMock = vi.fn(async () => Response.json({ ok: true, session_id: 'chat:1', rich_replies: null }));
    vi.stubGlobal('fetch', fetchMock);
    const { unmount } = renderSetting('chat:1', 'on');

    fireEvent.change(screen.getByRole('combobox', { name: 'Rich replies in this chat' }), { target: { value: 'default' } });
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(JSON.parse(String(init.body))).toEqual({ rich_replies: null });
    unmount();

    renderSetting(null, undefined);
    expect(screen.getByRole('combobox', { name: 'Rich replies in this chat' })).toBeDisabled();
  });
});
