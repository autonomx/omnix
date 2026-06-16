import { MantineProvider } from '@mantine/core';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { omnixModules } from '../../app/modules';
import { omnixTheme } from '../../design/theme';
import { ChatbotWorkspace } from './ChatbotWorkspace';

function renderChatbot() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  const module = omnixModules.find((entry) => entry.id === 'chatbot');

  if (!module) {
    throw new Error('Chatbot module is missing');
  }

  return render(
    <MantineProvider theme={omnixTheme} defaultColorScheme="dark">
      <QueryClientProvider client={queryClient}>
        <ChatbotWorkspace module={module} />
      </QueryClientProvider>
    </MantineProvider>,
  );
}

function requestPath(input: RequestInfo | URL): string {
  return typeof input === 'string' ? new URL(input, 'http://localhost').pathname : new URL(input.toString()).pathname;
}

function providerPayload() {
  return {
    providers: [
      {
        id: 'openai',
        label: 'OpenAI compatible',
        family: 'llm',
        source: 'settings',
        status: 'configured',
        capabilities: ['chat'],
      },
    ],
    models: [
      {
        id: 'gpt-mini',
        label: 'GPT mini',
        provider_id: 'openai',
        location: 'remote',
        capabilities: ['chat'],
      },
    ],
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('ChatbotWorkspace', () => {
  it('uses provider/model selectors and queues a chat generation job', async () => {
    let session: {
      id: string;
      title: string;
      provider_id: string;
      model_id: string;
      message_count: number;
      messages: Array<{ id: string; role: 'system' | 'user' | 'assistant'; content: string; created_at: string; metadata?: Record<string, unknown> }>;
      created_at: string;
      updated_at: string;
    } = {
      id: 'chat:1',
      title: 'Hello Omnix',
      provider_id: 'openai',
      model_id: 'gpt-mini',
      message_count: 0,
      messages: [],
      created_at: '2026-06-14T00:00:00Z',
      updated_at: '2026-06-14T00:00:00Z',
    };
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);

      if (path === '/api/providers') {
        return Response.json(providerPayload());
      }

      if (path === '/api/chat/sessions' && init?.method === 'POST') {
        return Response.json(session);
      }

      if (path === '/api/chat/sessions') {
        return Response.json({ sessions: [] });
      }

      if (path === '/api/chat/sessions/chat%3A1') {
        return Response.json(session);
      }

      if (path === '/api/chat/sessions/chat%3A1/messages') {
        session = {
          ...session,
          message_count: 1,
          messages: [
            {
              id: 'msg:1',
              role: 'user',
              content: 'Hello Omnix',
              created_at: '2026-06-14T00:00:01Z',
              metadata: { generation_status: 'queued' },
            },
          ],
        };
        return Response.json({
          generation_status: 'queued',
          session,
          user_message: session.messages[0],
          job: {
            id: 'job:1',
            module: 'chatbot',
            type: 'chat.generate',
            status: 'queued',
            resource_class: 'gpu:llm',
            created_at: '2026-06-14T00:00:01Z',
            updated_at: '2026-06-14T00:00:01Z',
            priority: 0,
          },
        });
      }

      return new Response('not found', { status: 404 });
    });
    vi.stubGlobal('fetch', fetchMock);

    renderChatbot();

    expect(await screen.findByText('No chat messages yet.')).toBeInTheDocument();
    expect(await screen.findByText('OpenAI compatible')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Provider'), { target: { value: 'openai' } });
    fireEvent.change(screen.getByLabelText('Model'), { target: { value: 'gpt-mini' } });
    fireEvent.change(screen.getByLabelText('Message'), { target: { value: 'Hello Omnix' } });
    fireEvent.click(screen.getByRole('button', { name: 'Queue response' }));

    expect(await screen.findByText('Generation job queued: job:1')).toBeInTheDocument();
    const transcriptMessage = screen.getAllByText('Hello Omnix').find((element) => within(element.closest('article') ?? element).queryByText('user'));
    expect(transcriptMessage).toBeTruthy();

    await waitFor(() => {
      const createCall = fetchMock.mock.calls.find(
        ([input, init]) => requestPath(input as RequestInfo | URL) === '/api/chat/sessions' && init?.method === 'POST',
      );
      const messageCall = fetchMock.mock.calls.find(
        ([input, init]) => requestPath(input as RequestInfo | URL).endsWith('/messages') && init?.method === 'POST',
      );
      expect(createCall?.[1]).toEqual(expect.objectContaining({ method: 'POST' }));
      expect(createCall?.[1]?.body).toContain('"provider_id":"openai"');
      expect(createCall?.[1]?.body).toContain('"model_id":"gpt-mini"');
      expect(messageCall?.[1]).toEqual(expect.objectContaining({ method: 'POST' }));
      expect(messageCall?.[1]?.body).toContain('"model_id":"gpt-mini"');
    });
  });

  it('surfaces gateway failures instead of silently doing nothing', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);

      if (path === '/api/providers') {
        return Response.json(providerPayload());
      }

      if (path === '/api/chat/sessions' && init?.method === 'POST') {
        return new Response('gateway offline', { status: 503 });
      }

      if (path === '/api/chat/sessions') {
        return Response.json({ sessions: [] });
      }

      return new Response('not found', { status: 404 });
    });
    vi.stubGlobal('fetch', fetchMock);

    renderChatbot();

    fireEvent.change(await screen.findByLabelText('Message'), { target: { value: 'Is this wired?' } });
    fireEvent.click(screen.getByRole('button', { name: 'Queue response' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('Chat request failed with status 503');
  });
});
