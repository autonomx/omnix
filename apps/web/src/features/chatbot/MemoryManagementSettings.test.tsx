import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { MemoryManagementPanel } from './MemoryManagementPanel';
import type { AssistantMemoryRuntimeStatus } from './memoryClient';

function renderPanel() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryManagementPanel sessionId="chat:one" />
    </QueryClientProvider>,
  );
}

function settings(curated = false): AssistantMemoryRuntimeStatus {
  return {
    settings: {
      curated_memory_enabled: curated,
      suggestions_enabled: false,
      history_recall_enabled: false,
      compaction_enabled: false,
      hermes_sync_enabled: false,
      require_approval_for_inferred_memory: true,
      memory_token_budget: 4000,
      history_token_budget: 8000,
      retention_days: 365,
      show_memory_use_indicator: true,
    },
    settings_path: '/tmp/settings.json',
    environment_overrides: [],
    approval_policy_locked: true,
    diagnostics_policy: 'content_free',
  };
}

afterEach(() => vi.unstubAllGlobals());

describe('MemoryManagementPanel settings', () => {
  it('shows server settings and persists an independent toggle', async () => {
    const updates: unknown[] = [];
    let current = settings(false);
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(input.toString(), 'http://localhost');
      if (url.pathname === '/api/assistant/memory/settings') {
        if (init?.method === 'POST') {
          const update = JSON.parse(String(init.body));
          updates.push(update);
          current = settings(Boolean(update.curated_memory_enabled));
        }
        return Response.json(current);
      }
      if (url.pathname.endsWith('/memory') && url.pathname.includes('/api/chat/sessions/')) {
        return Response.json({ session_id: 'chat:one', memory_enabled: false, memory_record_count: 0, snapshot: null });
      }
      if (url.pathname === '/api/assistant/memory/candidates/pending') {
        return Response.json({ session_id: 'chat:one', total: 0, candidates: [] });
      }
      if (url.pathname === '/api/assistant/memory') {
        return Response.json({ session_id: 'chat:one', total: 0, records: [] });
      }
      return new Response('not found', { status: 404 });
    });
    vi.stubGlobal('fetch', fetchMock);

    renderPanel();
    const toggle = await screen.findByRole('checkbox', { name: 'Use approved memory in Chat' });
    expect(toggle).not.toBeChecked();
    fireEvent.click(toggle);

    await waitFor(() => expect(updates).toEqual([{ curated_memory_enabled: true }]));
    expect(await screen.findByRole('status')).toHaveTextContent('Memory settings saved.');
  });

  it('disables environment-controlled settings and explains approval privacy', async () => {
    const controlled = settings(true);
    controlled.environment_overrides = ['curated_memory_enabled'];
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(input.toString(), 'http://localhost');
      if (url.pathname === '/api/assistant/memory/settings') return Response.json(controlled);
      if (url.pathname.endsWith('/memory') && url.pathname.includes('/api/chat/sessions/')) {
        return Response.json({ session_id: 'chat:one', memory_enabled: false, memory_record_count: 0, snapshot: null });
      }
      if (url.pathname === '/api/assistant/memory/candidates/pending') return Response.json({ session_id: 'chat:one', total: 0, candidates: [] });
      if (url.pathname === '/api/assistant/memory') return Response.json({ session_id: 'chat:one', total: 0, records: [] });
      return new Response('not found', { status: 404 });
    });
    vi.stubGlobal('fetch', fetchMock);

    renderPanel();

    const toggle = await screen.findByRole('checkbox', { name: /Use approved memory in Chat/ });
    expect(toggle).toBeDisabled();
    expect(screen.getByText(/Inferred memory approval is required and cannot be disabled/)).toBeInTheDocument();
  });
});
