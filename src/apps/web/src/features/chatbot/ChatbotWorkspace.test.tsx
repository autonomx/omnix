import { MantineProvider } from '@mantine/core';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { omnixModules } from '../../app/modules';
import { omnixTheme } from '../../design/theme';
import { ChatbotWorkspace, selectFreshChatSession } from './ChatbotWorkspace';

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

function assetPayload() {
  return {
    assets: [
      {
        id: 'voice-profile-1',
        type: 'voice_profile',
        module: 'voice-cloning',
        title: 'Ari Clone',
        storage_path: 'resources/voice_clones/ari-clone.json',
        metadata: { voice_id: 'ari-clone', profile_name: 'Ari Clone' },
        created_at: '2026-06-14T00:00:00Z',
        updated_at: '2026-06-14T00:00:00Z',
      },
    ],
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((innerResolve) => {
    resolve = innerResolve;
  });
  return { promise, resolve };
}

afterEach(() => {
  window.localStorage.clear();
  delete (window as typeof window & { __omnixLiveVoiceControllerInstalled?: boolean }).__omnixLiveVoiceControllerInstalled;
  delete (window as typeof window & { __omnixLiveVoiceUnifiedAudioInstalled?: boolean }).__omnixLiveVoiceUnifiedAudioInstalled;
  vi.useRealTimers();
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe('ChatbotWorkspace', () => {
  it('keeps the selected session when a previous mutation snapshot is still cached', () => {
    const previous = {
      id: 'chat:previous',
      message_count: 8,
      messages: [{ id: 'msg:previous', role: 'assistant', content: 'Previous chat' }],
    };
    const selected = {
      id: 'chat:selected',
      message_count: 2,
      messages: [
        { id: 'msg:selected-user', role: 'user', content: 'Selected chat' },
        { id: 'msg:selected-assistant', role: 'assistant', content: 'Selected reply' },
      ],
    };

    expect(selectFreshChatSession(previous, selected)).toBe(selected);
  });

  it('prefers the fuller transcript when response counts tie', () => {
    const queued = {
      id: 'chat:research',
      message_count: 4,
      messages: [
        { id: 'msg:recent-user', role: 'user', content: 'Recent prompt' },
        { id: 'msg:recent-assistant', role: 'assistant', content: 'Recent answer' },
      ],
    };
    const refreshed = {
      id: 'chat:research',
      message_count: 4,
      messages: [
        { id: 'msg:old-user', role: 'user', content: 'Earlier prompt' },
        { id: 'msg:old-assistant', role: 'assistant', content: 'Earlier answer' },
        ...queued.messages,
      ],
    };

    expect(selectFreshChatSession(queued, refreshed)).toBe(refreshed);
  });

  it('prefers a refreshed session over the queued mutation snapshot', () => {
    const queued = {
      id: 'chat:research',
      message_count: 1,
      messages: [{ id: 'msg:user', role: 'user', content: 'Research this' }],
    };
    const refreshed = {
      id: 'chat:research',
      message_count: 2,
      messages: [
        { id: 'msg:user', role: 'user', content: 'Research this' },
        { id: 'msg:assistant', role: 'assistant', content: 'Research result' },
      ],
    };

    expect(selectFreshChatSession(queued, refreshed)).toBe(refreshed);
  });

  it('shows chat loading states instead of empty states while sessions are pending', async () => {
    const sessions = deferred<Response>();
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = requestPath(input);

      if (path === '/api/providers') {
        return Response.json(providerPayload());
      }

      if (path === '/api/assets') {
        return Response.json(assetPayload());
      }

      if (path === '/api/chat/sessions') {
        return sessions.promise;
      }

      return new Response('not found', { status: 404 });
    });
    vi.stubGlobal('fetch', fetchMock);

    renderChatbot();

    expect(await screen.findByText('Loading chat sessions...')).toBeInTheDocument();
    expect(screen.getByText('Loading chat messages...')).toBeInTheDocument();
    expect(screen.queryByText('No chat sessions yet.')).not.toBeInTheDocument();
    expect(screen.queryByText('No chat messages yet.')).not.toBeInTheDocument();

    sessions.resolve(Response.json({ sessions: [] }));

    expect(await screen.findByText('No chat sessions yet.')).toBeInTheDocument();
    expect(await screen.findByText('No chat messages yet.')).toBeInTheDocument();
  });

  it('opens a dedicated Characters destination from the assistant sidebar', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = requestPath(input);

      if (path === '/api/providers') return Response.json(providerPayload());
      if (path === '/api/assets') return Response.json(assetPayload());
      if (path === '/api/chat/sessions') return Response.json({ sessions: [] });
      if (path === '/api/characters') return Response.json({ characters: [] });

      return new Response('not found', { status: 404 });
    });
    vi.stubGlobal('fetch', fetchMock);

    renderChatbot();

    fireEvent.click(await screen.findByRole('button', { name: 'Open Characters view' }));

    expect(await screen.findByRole('heading', { name: 'Characters' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Profiles and relationship data' })).toBeInTheDocument();
    expect(await screen.findByText('No characters have been created.')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Memory' })).not.toBeInTheDocument();
  });

  it('opens an existing chat scrolled to the latest message', async () => {
    const scrollIntoViewMock = vi.fn();
    Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
      configurable: true,
      value: scrollIntoViewMock,
    });
    const session = {
      id: 'chat:scroll',
      title: 'Long chat',
      provider_id: 'openai',
      model_id: 'gpt-mini',
      message_count: 3,
      messages: [
        { id: 'msg:old', role: 'user', content: 'Oldest message', created_at: '2026-06-14T00:00:01Z' },
        { id: 'msg:middle', role: 'assistant', content: 'Middle message', created_at: '2026-06-14T00:00:02Z' },
        { id: 'msg:latest', role: 'assistant', content: 'Newest message', created_at: '2026-06-14T00:00:03Z' },
      ],
      created_at: '2026-06-14T00:00:00Z',
      updated_at: '2026-06-14T00:00:03Z',
    };
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = requestPath(input);

      if (path === '/api/providers') {
        return Response.json(providerPayload());
      }

      if (path === '/api/assets') {
        return Response.json(assetPayload());
      }

      if (path === '/api/chat/sessions') {
        return Response.json({ sessions: [session] });
      }

      if (path === '/api/chat/sessions/chat%3Ascroll') {
        return Response.json(session);
      }

      return new Response('not found', { status: 404 });
    });
    vi.stubGlobal('fetch', fetchMock);

    renderChatbot();

    expect((await screen.findAllByText('Newest message')).length).toBeGreaterThan(0);
    await waitFor(() => {
      expect(scrollIntoViewMock).toHaveBeenCalledWith({ block: 'end', behavior: 'auto' });
    });
  });

  it('uses provider/model selectors and renders the assistant response with activity events', async () => {
    vi.stubEnv('VITE_ASSISTANT_TTS_URL', 'http://tts.local');
    vi.stubEnv('VITE_ASSISTANT_TTS_VOICE', 'narrator-clone');
    const playMock = vi.fn().mockResolvedValue(undefined);
    const audioCtor = vi.fn().mockImplementation((src: string) => ({ src, play: playMock }));
    const writeTextMock = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal('Audio', audioCtor);
    Object.assign(navigator, { clipboard: { writeText: writeTextMock } });

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

      if (path === '/api/assets') {
        return Response.json(assetPayload());
      }

      if (path === '/synthesize') {
        return Response.json({
          audioBase64: 'UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA=',
          mimeType: 'audio/wav',
        });
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
          message_count: 2,
          messages: [
            {
              id: 'msg:1',
              role: 'user',
              content: 'Hello Omnix',
              created_at: '2026-06-14T00:00:01Z',
              metadata: { generation_status: 'completed' },
            },
            {
              id: 'msg:2',
              role: 'assistant',
              content: 'Provider reply from the selected model.',
              created_at: '2026-06-14T00:00:02Z',
              metadata: { generation_status: 'completed' },
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
    expect(await screen.findByRole('option', { name: 'Ari Clone' })).toBeInTheDocument();
    expect(screen.getByText('Mic input')).toBeInTheDocument();
    const chatHeader = screen.getByRole('heading', { name: 'Hey! How are you today?' }).closest('header');
    expect(chatHeader).not.toBeNull();
    expect(within(chatHeader as HTMLElement).queryByRole('button', { name: /Tools/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Share' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Star conversation' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'More actions' })).not.toBeInTheDocument();
    expect(screen.getByText('Workspace activity')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Cloned voice'), { target: { value: 'ari-clone' } });
    expect(screen.getByLabelText('Cloned voice')).toHaveValue('ari-clone');
    expect(JSON.parse(window.localStorage.getItem('omnix.chatbot.assistantSettings') ?? '{}')).toMatchObject({ voiceId: 'ari-clone' });

    fireEvent.click(screen.getByRole('button', { name: 'Open Settings view' }));
    expect(screen.getByLabelText('Live mic sensitivity')).toHaveValue('55');
    fireEvent.change(screen.getByLabelText('Live mic sensitivity'), { target: { value: '35' } });
    expect(JSON.parse(window.localStorage.getItem('omnix.chatbot.assistantSettings') ?? '{}')).toMatchObject({ liveVoiceSensitivity: 35 });
    fireEvent.click(screen.getByRole('button', { name: 'Open Chats view' }));

    fireEvent.click(screen.getByRole('button', { name: 'Tell me a fun fact' }));
    expect(screen.getByLabelText('Message')).toHaveValue('Tell me a fun fact');
    fireEvent.change(screen.getByLabelText('Provider'), { target: { value: 'openai' } });
    fireEvent.change(screen.getByLabelText('Model'), { target: { value: 'gpt-mini' } });
    fireEvent.change(screen.getByLabelText('Message'), { target: { value: 'Hello Omnix' } });
    fireEvent.click(screen.getByRole('button', { name: 'Queue response' }));

    expect(await screen.findByText('Response ready: job:1')).toBeInTheDocument();
    expect((await screen.findAllByText('Provider reply from the selected model.')).length).toBeGreaterThan(0);
    expect(await screen.findByText('Source: assistant_message')).toBeInTheDocument();
    const transcriptMessage = screen.getAllByText('Hello Omnix').find((element) => within(element.closest('article') ?? element).queryByText('You'));
    expect(transcriptMessage ?? screen.getByText('Hello Omnix')).toBeTruthy();
    const voiceTranscript = screen.getByText('Transcript').closest('.assistant-voice-transcript');
    expect(voiceTranscript).not.toBeNull();
    expect(within(voiceTranscript as HTMLElement).getByText('Provider reply from the selected model.')).toBeInTheDocument();
    fireEvent.click(within(voiceTranscript as HTMLElement).getByRole('button', { name: 'Clear' }));
    expect(within(voiceTranscript as HTMLElement).queryByText('Provider reply from the selected model.')).not.toBeInTheDocument();
    expect(within(voiceTranscript as HTMLElement).getByText('Voice transcript will appear here during live calls.')).toBeInTheDocument();

    expect(screen.getAllByRole('button', { name: 'Play response audio' }).length).toBeGreaterThan(0);
    fireEvent.click(screen.getAllByRole('button', { name: 'Like response' })[0]);
    expect(screen.getAllByRole('button', { name: 'Like response' })[0]).toHaveAttribute('aria-pressed', 'true');
    fireEvent.click(screen.getAllByRole('button', { name: 'Copy response' })[0]);
    await waitFor(() => expect(writeTextMock).toHaveBeenCalledWith('Provider reply from the selected model.'));
    fireEvent.click(screen.getAllByRole('button', { name: 'More response actions' })[0]);
    expect(screen.getByRole('menuitem', { name: 'Copy text' })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: 'Play audio' })).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole('button', { name: 'Play response audio' })[0]);

    await waitFor(() => {
      const playedAudio = audioCtor.mock.calls.length > 0 && playMock.mock.calls.length > 0;
      const voiceStatus = screen.queryAllByText(/Playing response voice|Playing cloned response voice|Configure VITE_ASSISTANT_TTS_URL|Voice Studio|Omnix API request failed/).length > 0;
      expect(playedAudio || voiceStatus).toBeTruthy();
    });

    await waitFor(() => {
      const persistedEvents = JSON.parse(window.localStorage.getItem('omnix.assistantWorkspace.events') ?? '[]') as unknown[];
      expect(persistedEvents).toHaveLength(2);
    });

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

  it('starts, advances, and resets the live call timer from call controls', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = requestPath(input);

      if (path === '/api/providers') {
        return Response.json(providerPayload());
      }

      if (path === '/api/assets') {
        return Response.json(assetPayload());
      }

      if (path === '/api/chat/sessions') {
        return Response.json({ sessions: [] });
      }

      return new Response('not found', { status: 404 });
    });
    vi.stubGlobal('fetch', fetchMock);

    renderChatbot();

    expect(await screen.findByText('No chat messages yet.')).toBeInTheDocument();
    expect(screen.getByText('00:00:00')).toBeInTheDocument();
    expect(screen.getByText('Disconnected')).toBeInTheDocument();

    vi.useFakeTimers();
    fireEvent.click(screen.getByRole('button', { name: 'Start Call' }));

    expect(screen.getByText('Connected')).toBeInTheDocument();
    expect(screen.queryByText('Live voice call started.') ?? screen.queryByText(/Browser speech recognition/)).toBeTruthy();
    act(() => {
      window.dispatchEvent(new CustomEvent('omnix:assistant-voice-interrupt'));
    });
    expect(screen.getByText('Interrupted. Listening for your next message.')).toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(65_000);
    });

    expect(screen.getByText('00:01:05')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'End Call' }));

    expect(screen.getByText('00:00:00')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Start Call' })).toBeInTheDocument();
    expect(screen.getByText('Live voice call ended.')).toBeInTheDocument();
  });

  it('auto-sends finalized live speech into the chat stream', async () => {
    let recognitionInstance: {
      continuous: boolean;
      interimResults: boolean;
      lang: string;
      onresult: ((event: unknown) => void) | null;
      onerror: ((event: unknown) => void) | null;
      onend: (() => void) | null;
      start: ReturnType<typeof vi.fn>;
      stop: ReturnType<typeof vi.fn>;
      abort: ReturnType<typeof vi.fn>;
    } | null = null;

    class FakeSpeechRecognition {
      continuous = false;
      interimResults = false;
      lang = '';
      onresult: ((event: unknown) => void) | null = null;
      onerror: ((event: unknown) => void) | null = null;
      onend: (() => void) | null = null;
      start = vi.fn();
      stop = vi.fn();
      abort = vi.fn();

      constructor() {
        recognitionInstance = this;
      }
    }

    vi.stubGlobal('SpeechRecognition', FakeSpeechRecognition);

    let session = {
      id: 'chat:voice-auto',
      title: 'Voice command',
      provider_id: 'openai',
      model_id: 'gpt-mini',
      message_count: 0,
      messages: [] as Array<{ id: string; role: 'system' | 'user' | 'assistant'; content: string; created_at: string }>,
      created_at: '2026-06-14T00:00:00Z',
      updated_at: '2026-06-14T00:00:00Z',
    };
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);

      if (path === '/api/providers') return Response.json(providerPayload());
      if (path === '/api/assets') return Response.json(assetPayload());
      if (path === '/api/chat/sessions' && init?.method === 'POST') return Response.json(session);
      if (path === '/api/chat/sessions') return Response.json({ sessions: [] });
      if (path === '/api/chat/sessions/chat%3Avoice-auto/messages/stream') {
        session = {
          ...session,
          message_count: 2,
          messages: [
            { id: 'msg:voice-user', role: 'user', content: 'open the pod bay doors', created_at: '2026-06-14T00:00:01Z' },
            { id: 'msg:voice-assistant', role: 'assistant', content: 'Opening them now.', created_at: '2026-06-14T00:00:02Z' },
          ],
        };
        return new Response(
          [
            'data: {"type":"text_chunk","text":"Opening them now."}\n\n',
            `data: ${JSON.stringify({ type: 'session', session })}\n\n`,
            'data: {"type":"done"}\n\n',
          ].join(''),
          { headers: { 'Content-Type': 'text/event-stream' } },
        );
      }

      return new Response('not found', { status: 404 });
    });
    vi.stubGlobal('fetch', fetchMock);

    renderChatbot();

    await screen.findByText('No chat messages yet.');
    fireEvent.click(screen.getByLabelText('Auto-speak assistant replies'));
    fireEvent.click(screen.getByRole('button', { name: 'Start Call' }));

    await waitFor(() => expect(recognitionInstance).not.toBeNull());

    act(() => {
      window.dispatchEvent(new CustomEvent('omnix:assistant-voice-perf', {
        detail: { stage: 'stt_final_requested', turnId: 'voice-turn:test-auto' },
      }));
      window.dispatchEvent(new CustomEvent('omnix:assistant-voice-perf', {
        detail: {
          stage: 'stt_final_received',
          turnId: 'voice-turn:test-auto',
          transcriptChars: 22,
          sttFinalizeMs: 180,
        },
      }));
      recognitionInstance?.onresult?.({
        resultIndex: 0,
        results: {
          length: 1,
          0: { isFinal: true, 0: { transcript: 'open the pod bay doors' } },
        },
      });
    });

    expect(screen.getByText('open the pod bay doors')).toBeInTheDocument();

    await act(async () => {
      await new Promise((resolve) => window.setTimeout(resolve, 950));
    });

    await waitFor(() => {
      const streamCall = fetchMock.mock.calls.find(
        ([input, init]) => requestPath(input as RequestInfo | URL).endsWith('/messages/stream') && init?.method === 'POST',
      );
      expect(streamCall?.[1]?.body).toContain('"content":"open the pod bay doors"');
    });
    expect((await screen.findAllByText('Opening them now.')).length).toBeGreaterThan(0);
    await waitFor(() => {
      const diagnosticBodies = fetchMock.mock.calls
        .filter(([input, init]) => requestPath(input as RequestInfo | URL) === '/api/tts/live-call/diagnostics' && init?.method === 'POST')
        .map(([, init]) => String(init?.body ?? ''))
        .join('\n');
      expect(diagnosticBodies).toContain('"trace_id":"live-call:voice-turn:test-auto"');
      expect(diagnosticBodies).toContain('"event":"chat_submit_started"');
      expect(diagnosticBodies).toContain('"event":"chat_response_opened"');
      expect(diagnosticBodies).toContain('"event":"llm_first_text_chunk_received"');
      expect(diagnosticBodies).toContain('"event":"llm_stream_completed"');
      expect(diagnosticBodies).not.toContain('open the pod bay doors');
      expect(diagnosticBodies).not.toContain('Opening them now.');
    });

    act(() => {
      recognitionInstance?.onresult?.({
        resultIndex: 0,
        results: {
          length: 1,
          0: { isFinal: true, 0: { transcript: 'Open the pod bay doors!' } },
        },
      });
    });
    await act(async () => {
      await new Promise((resolve) => window.setTimeout(resolve, 950));
    });
    const streamCalls = fetchMock.mock.calls.filter(
      ([input, init]) => requestPath(input as RequestInfo | URL).endsWith('/messages/stream') && init?.method === 'POST',
    );
    expect(streamCalls).toHaveLength(1);
  });

  it('streams main composer submissions while a live call is active', async () => {
    class FakeSpeechRecognition {
      continuous = false;
      interimResults = false;
      lang = '';
      onresult: ((event: unknown) => void) | null = null;
      onerror: ((event: unknown) => void) | null = null;
      onend: (() => void) | null = null;
      start = vi.fn();
      stop = vi.fn();
      abort = vi.fn();
    }

    vi.stubGlobal('SpeechRecognition', FakeSpeechRecognition);

    let session = {
      id: 'chat:live-typed',
      title: 'Live typed',
      provider_id: 'openai',
      model_id: 'gpt-mini',
      message_count: 0,
      messages: [] as Array<{ id: string; role: 'system' | 'user' | 'assistant'; content: string; created_at: string }>,
      created_at: '2026-06-14T00:00:00Z',
      updated_at: '2026-06-14T00:00:00Z',
    };
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);

      if (path === '/api/providers') return Response.json(providerPayload());
      if (path === '/api/assets') return Response.json(assetPayload());
      if (path === '/api/chat/sessions' && init?.method === 'POST') return Response.json(session);
      if (path === '/api/chat/sessions') return Response.json({ sessions: [] });
      if (path === '/api/chat/sessions/chat%3Alive-typed/messages') {
        return new Response('typed live call should stream', { status: 500 });
      }
      if (path === '/api/chat/sessions/chat%3Alive-typed/messages/stream') {
        session = {
          ...session,
          message_count: 2,
          messages: [
            { id: 'msg:typed-user', role: 'user', content: 'can you see the screen?', created_at: '2026-06-14T00:00:01Z' },
            { id: 'msg:typed-assistant', role: 'assistant', content: 'I can see it now.', created_at: '2026-06-14T00:00:02Z' },
          ],
        };
        return new Response(
          [
            'data: {"type":"text_chunk","text":"I can see it now."}\n\n',
            `data: ${JSON.stringify({ type: 'session', session })}\n\n`,
            'data: {"type":"done"}\n\n',
          ].join(''),
          { headers: { 'Content-Type': 'text/event-stream' } },
        );
      }

      return new Response('not found', { status: 404 });
    });
    vi.stubGlobal('fetch', fetchMock);

    renderChatbot();

    await screen.findByText('No chat messages yet.');
    fireEvent.click(screen.getByRole('button', { name: 'Start Call' }));
    fireEvent.change(screen.getByLabelText('Message'), { target: { value: 'can you see the screen?' } });
    fireEvent.click(screen.getByRole('button', { name: 'Queue response' }));

    await waitFor(() => {
      const streamCall = fetchMock.mock.calls.find(
        ([input, init]) => requestPath(input as RequestInfo | URL).endsWith('/messages/stream') && init?.method === 'POST',
      );
      expect(streamCall?.[1]?.body).toContain('"content":"can you see the screen?"');
    });
    expect(fetchMock.mock.calls.some(
      ([input, init]) => requestPath(input as RequestInfo | URL).endsWith('/messages') && init?.method === 'POST',
    )).toBe(false);
    expect((await screen.findAllByText('I can see it now.')).length).toBeGreaterThan(0);
  });

  it('submits the composer with Enter and preserves Shift+Enter for new lines', async () => {
    let session = {
      id: 'chat:enter',
      title: 'Keyboard submit',
      provider_id: 'openai',
      model_id: 'gpt-mini',
      message_count: 0,
      messages: [] as Array<{ id: string; role: 'system' | 'user' | 'assistant'; content: string; created_at: string }>,
      created_at: '2026-06-14T00:00:00Z',
      updated_at: '2026-06-14T00:00:00Z',
    };
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);

      if (path === '/api/providers') {
        return Response.json(providerPayload());
      }

      if (path === '/api/assets') {
        return Response.json(assetPayload());
      }

      if (path === '/api/chat/sessions' && init?.method === 'POST') {
        return Response.json(session);
      }

      if (path === '/api/chat/sessions') {
        return Response.json({ sessions: [] });
      }

      if (path === '/api/chat/sessions/chat%3Aenter/messages') {
        session = {
          ...session,
          message_count: 2,
          messages: [
            { id: 'msg:keyboard-user', role: 'user', content: 'Send from keyboard', created_at: '2026-06-14T00:00:01Z' },
            { id: 'msg:keyboard-assistant', role: 'assistant', content: 'Keyboard response.', created_at: '2026-06-14T00:00:02Z' },
          ],
        };
        return Response.json({
          generation_status: 'queued',
          session,
          user_message: session.messages[0],
          job: {
            id: 'job:keyboard',
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

    const messageInput = await screen.findByLabelText('Message');
    fireEvent.change(messageInput, { target: { value: 'Send from keyboard' } });
    fireEvent.keyDown(messageInput, { key: 'Enter', shiftKey: true });

    expect(fetchMock.mock.calls.some(([input, init]) => requestPath(input as RequestInfo | URL) === '/api/chat/sessions' && init?.method === 'POST')).toBe(false);

    fireEvent.keyDown(messageInput, { key: 'Enter' });

    expect(await screen.findByText('Response ready: job:keyboard')).toBeInTheDocument();
    await waitFor(() => {
      const messageCall = fetchMock.mock.calls.find(
        ([input, init]) => requestPath(input as RequestInfo | URL).endsWith('/messages') && init?.method === 'POST',
      );
      expect(messageCall?.[1]?.body).toContain('"content":"Send from keyboard"');
    });
  });

  it('surfaces gateway failures in the replayable activity stream', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);

      if (path === '/api/providers') {
        return Response.json(providerPayload());
      }

      if (path === '/api/assets') {
        return Response.json(assetPayload());
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
    expect(await screen.findByText('chat request failed: Chat request failed with status 503')).toBeInTheDocument();
    expect(await screen.findByText('Source: operation_failed')).toBeInTheDocument();

    await waitFor(() => {
      const persistedEvents = JSON.parse(window.localStorage.getItem('omnix.assistantWorkspace.events') ?? '[]') as Array<{
        type?: string;
        payload?: { operation?: string; statusCode?: number; details?: { submittedContent?: string } };
      }>;
      expect(persistedEvents).toHaveLength(1);
      expect(persistedEvents[0]).toMatchObject({
        type: 'operation_failed',
        payload: {
          operation: 'chat_request',
          statusCode: 503,
          details: { submittedContent: 'Is this wired?' },
        },
      });
    });
  });
});
