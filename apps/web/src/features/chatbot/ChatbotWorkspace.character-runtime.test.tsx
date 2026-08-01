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
  if (!module) throw new Error('Chatbot module is missing');

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

const session = {
  id: 'chat:maya',
  title: 'Live Chat with Maya',
  provider_id: 'openai',
  model_id: 'gpt-mini',
  interaction_mode: 'character',
  character_id: 'maya',
  voice_asset_id: 'voice-cloning:maya',
  read_memory: false,
  write_memory: false,
  shared_memory_access: 'none',
  transcript_policy: 'persistent',
  character_profile_version: 3,
  effective_identity_hash: 'a'.repeat(64),
  message_count: 1,
  messages: [{
    id: 'msg:maya',
    role: 'assistant',
    content: 'Hello from Maya.',
    created_at: '2026-07-30T20:00:00Z',
  }],
  created_at: '2026-07-30T20:00:00Z',
  updated_at: '2026-07-30T20:00:00Z',
};

const runtime = {
  session_id: session.id,
  interaction_mode: 'character',
  display_name: 'Maya',
  character_id: 'maya',
  character_profile_version: 3,
  effective_identity_hash: session.effective_identity_hash,
  voice_asset_id: 'voice-cloning:maya',
  greeting: '',
  avatar_pack: null,
  speech_style: {
    speed: 1,
    temperature: 0.6,
    top_k: 20,
    top_p: 0.85,
    repetition_penalty: 1,
    expressiveness: 'warm',
    emotion: 'friendly',
    interruption_style: 'balanced',
  },
  read_memory: false,
  write_memory: false,
  shared_memory_access: 'none',
  memory_snapshot_id: null,
  preload: {
    profile_loaded: true,
    voice_resolved: true,
    avatar_pack_loaded: false,
    memory_snapshot_loaded: false,
    memory_record_count: 0,
    preload_ms: 4,
    resolved_at: '2026-07-30T20:00:00Z',
  },
};

afterEach(() => {
  window.localStorage.clear();
  delete (window as typeof window & { __omnixLiveVoiceControllerInstalled?: boolean }).__omnixLiveVoiceControllerInstalled;
  vi.unstubAllGlobals();
});

describe('ChatbotWorkspace character runtime projection', () => {
  it('keeps the active character projected before, during, and after a live call', async () => {
    Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
      configurable: true,
      value: vi.fn(),
    });
    (window as typeof window & { __omnixLiveVoiceControllerInstalled?: boolean }).__omnixLiveVoiceControllerInstalled = true;

    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = requestPath(input);
      if (path === '/api/providers') return Response.json({
        providers: [{ id: 'openai', label: 'OpenAI compatible', family: 'llm', source: 'settings', status: 'configured', capabilities: ['chat'] }],
        models: [{ id: 'gpt-mini', label: 'GPT mini', provider_id: 'openai', location: 'remote', capabilities: ['chat'] }],
      });
      if (path === '/api/assets') return Response.json({
        assets: [{
          id: 'voice-cloning:maya',
          type: 'voice_profile',
          module: 'voice-cloning',
          title: 'Maya Clone',
          storage_path: 'resources/voice_clones/maya.json',
          metadata: { voice_id: 'maya-clone', profile_name: 'Maya Clone' },
          created_at: '2026-07-30T20:00:00Z',
          updated_at: '2026-07-30T20:00:00Z',
        }],
      });
      if (path === '/api/chat/sessions') return Response.json({ sessions: [session] });
      if (path === '/api/chat/sessions/chat%3Amaya') return Response.json(session);
      if (path === '/api/chat/sessions/chat%3Amaya/interaction') return Response.json(session);
      if (path === '/api/chat/sessions/chat%3Amaya/live-call/runtime') return Response.json(runtime);
      return new Response('not found', { status: 404 });
    });
    vi.stubGlobal('fetch', fetchMock);

    renderChatbot();

    expect(await screen.findByText('Character Mode · Maya')).toBeInTheDocument();
    expect(screen.getByLabelText('Cloned voice')).toBeDisabled();
    expect(screen.getByLabelText('Cloned voice')).toHaveValue('maya-clone');
    expect(screen.getByPlaceholderText('Message Maya, or use the microphone…')).toBeInTheDocument();

    const message = screen.getAllByText('Hello from Maya.')
      .map((element) => element.closest('article'))
      .find((element): element is HTMLElement => element instanceof HTMLElement);
    expect(message).toBeDefined();
    expect(within(message as HTMLElement).getByText('Maya')).toBeInTheDocument();

    const transcript = screen.getByText('Transcript').closest('.assistant-voice-transcript');
    expect(transcript).not.toBeNull();
    expect(within(transcript as HTMLElement).getByText('Maya')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Start Call' }));
    expect(await screen.findByText('Connected')).toBeInTheDocument();
    expect(screen.getByText('Character Mode · Maya')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'End Call' }));
    await waitFor(() => expect(screen.getByText('Disconnected')).toBeInTheDocument());
    expect(screen.getByText('Character Mode · Maya')).toBeInTheDocument();
    expect(screen.getByLabelText('Cloned voice')).toBeDisabled();
  });
});
