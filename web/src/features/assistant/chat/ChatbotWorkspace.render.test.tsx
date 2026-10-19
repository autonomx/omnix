import { MantineProvider } from '@mantine/core';
import { QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { omnixModules } from '../../../app/modules';
import { omnixTheme } from '../../../design/theme';
import { ChatbotWorkspace } from './ChatbotWorkspace';
import { ChatMessageItem } from './ChatMessageItem';
import { renderMarkdownHtml } from './markdownRenderer';
import { createTestQueryClient } from '../../../test/renderWithProviders';

// Counts message renders: a rendered message turns its markdown into HTML.
vi.mock('./markdownRenderer', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./markdownRenderer')>();
  return { ...actual, renderMarkdownHtml: vi.fn(actual.renderMarkdownHtml) };
});

const session = {
  id: 'chat:typing',
  title: 'Typing chat',
  provider_id: 'openai',
  model_id: 'gpt-mini',
  message_count: 2,
  messages: [
    { id: 'msg:user', role: 'user', content: 'What is **new**?', created_at: '2026-06-14T00:00:01Z' },
    { id: 'msg:assistant', role: 'assistant', content: 'A *few* things.', created_at: '2026-06-14T00:00:02Z' },
  ],
  created_at: '2026-06-14T00:00:00Z',
  updated_at: '2026-06-14T00:00:02Z',
};

function respond(input: RequestInfo | URL): Response {
  const path = new URL(String(input), 'http://localhost').pathname;
  if (path === '/api/providers') {
    return Response.json({
      providers: [{ id: 'openai', label: 'OpenAI compatible', family: 'llm', source: 'settings', status: 'configured', capabilities: ['chat'] }],
      models: [{ id: 'gpt-mini', provider_id: 'openai', label: 'GPT Mini', capabilities: ['chat'] }],
    });
  }
  if (path === '/api/assets') return Response.json({ assets: [] });
  if (path === '/api/chat/sessions') return Response.json({ sessions: [session] });
  if (path === '/api/chat/sessions/chat%3Atyping') return Response.json(session);
  return new Response('not found', { status: 404 });
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.localStorage.clear();
});

describe('Chat rendering', () => {
  it('does not re-render the transcript while the user types', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => respond(input)));
    const module = omnixModules.find((entry) => entry.id === 'chatbot');
    if (!module) throw new Error('Chatbot module is missing');
    render(
      <MantineProvider theme={omnixTheme} defaultColorScheme="dark">
        <QueryClientProvider client={createTestQueryClient()}>
          <ChatbotWorkspace module={module} />
        </QueryClientProvider>
      </MantineProvider>,
    );
    expect((await screen.findAllByText('few')).length).toBeGreaterThan(0);
    const rendersBeforeTyping = vi.mocked(renderMarkdownHtml).mock.calls.length;

    const composer = screen.getByRole('textbox', { name: 'Message' });
    for (const text of ['H', 'He', 'Hel', 'Hell', 'Hello']) fireEvent.input(composer, { target: { value: text } });

    expect(composer).toHaveValue('Hello');
    expect(vi.mocked(renderMarkdownHtml).mock.calls.length).toBe(rendersBeforeTyping);
  });
});

// Generative UI in the transcript (GUI-2.2, GUI-2.4).
const uiContent = 'Revenue held.\n\n```omnix-ui\n{"type": "stats", "items": [{"label": "Revenue", "value": "$6,930"}]}\n```';
const uiPayload = {
  version: 1,
  compiler_version: 'gui-compiler-1',
  compiled_at: '2026-10-11T00:00:00Z',
  segments: [{ kind: 'markdown', start: 0, end: 15 }, { kind: 'block', id: 'b1', text: 'Revenue: $6,930.' }],
  blocks: { b1: { type: 'stats', id: 'b1', v: 1, items: [{ label: 'Revenue', value: '$6,930' }], provenance: 'model', bindings: [] } },
  text: 'Revenue held.\n\nRevenue: $6,930.',
  speech: 'Revenue held.\n\nRevenue $6,930.',
  diagnostics: [],
};
const uiSession = {
  ...session,
  id: 'chat:ui',
  message_count: 4,
  messages: [
    { id: 'msg:q1', role: 'user', content: 'How was the quarter?', created_at: '2026-06-14T00:00:01Z' },
    { id: 'msg:ui', role: 'assistant', content: uiContent, created_at: '2026-06-14T00:00:02Z', metadata: { ui: uiPayload } },
    { id: 'msg:q2', role: 'user', content: 'Thanks', created_at: '2026-06-14T00:00:03Z' },
    { id: 'msg:plain', role: 'assistant', content: 'A *few* things.', created_at: '2026-06-14T00:00:04Z' },
  ],
};

function respondWithUi(input: RequestInfo | URL): Response {
  const path = new URL(String(input), 'http://localhost').pathname;
  if (path === '/api/chat/sessions') return Response.json({ sessions: [uiSession] });
  if (path === '/api/chat/sessions/chat%3Aui') return Response.json(uiSession);
  return respond(input);
}

function renderWorkspace() {
  const module = omnixModules.find((entry) => entry.id === 'chatbot');
  if (!module) throw new Error('Chatbot module is missing');
  return render(
    <MantineProvider theme={omnixTheme} defaultColorScheme="dark">
      <QueryClientProvider client={createTestQueryClient()}>
        <ChatbotWorkspace module={module} />
      </QueryClientProvider>
    </MantineProvider>,
  );
}

describe('Chat generative UI rendering', () => {
  it('renders a stored block reply as components and a plain reply exactly as before', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => respondWithUi(input)));
    const { container } = renderWorkspace();

    const stats = await screen.findByRole('region', { name: 'Headline figures' });
    expect(stats).toHaveTextContent('$6,930');
    const uiWrapper = container.querySelector('[data-message-id="msg:ui"]');
    expect(uiWrapper).toHaveClass('assistant-message-content', 'assistant-ui-reply');
    expect(uiWrapper).toHaveAttribute('data-raw-content', uiContent);
    expect(uiWrapper?.textContent).not.toContain('omnix-ui');

    const plainWrapper = container.querySelector('[data-message-id="msg:plain"]');
    expect(plainWrapper?.className).toBe('assistant-message-content');
    expect(plainWrapper?.innerHTML).toBe(renderMarkdownHtml('A *few* things.', undefined));
  });

  it('copies the text projection of a block reply, never its JSON', async () => {
    const writeText = vi.fn(async () => undefined);
    vi.stubGlobal('navigator', { ...navigator, clipboard: { writeText } });
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => respondWithUi(input)));
    renderWorkspace();

    await screen.findByRole('region', { name: 'Headline figures' });
    fireEvent.click(screen.getAllByRole('button', { name: 'Copy response' })[0]);

    await vi.waitFor(() => expect(writeText).toHaveBeenCalledWith('Revenue held.\n\nRevenue: $6,930.'));
  });
});

describe('ChatMessageItem with generative UI', () => {
  const actions = {
    toggleFeedback: vi.fn(), copy: vi.fn(), play: vi.fn(), stream: vi.fn(), toggleMenu: vi.fn(), closeMenu: vi.fn(),
    continueFrom: vi.fn(), openTools: vi.fn(), chooseUiOption: vi.fn(), fillComposerFromUi: vi.fn(),
  };
  const client = createTestQueryClient();
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  const uiMessage = uiSession.messages[1] as Parameters<typeof ChatMessageItem>[0]['message'];
  const plainMessage = uiSession.messages[3] as Parameters<typeof ChatMessageItem>[0]['message'];

  it('plays the speech projection of a block reply', () => {
    render(<ChatMessageItem message={uiMessage} sessionId="chat:ui" feedback={undefined} menuOpen={false} streaming={false} actions={actions} />, { wrapper });
    fireEvent.click(screen.getByRole('button', { name: 'Play response audio' }));

    expect(actions.play).toHaveBeenCalledWith('Revenue held.\n\nRevenue $6,930.');
  });

  it('re-renders only the message whose props changed', () => {
    const list = (plain: typeof plainMessage) => (
      <>
        <ChatMessageItem message={uiMessage} sessionId="chat:ui" feedback={undefined} menuOpen={false} streaming={false} actions={actions} />
        <ChatMessageItem message={plain} sessionId="chat:ui" feedback={undefined} menuOpen={false} streaming={false} actions={actions} />
      </>
    );
    const { rerender } = render(list(plainMessage), { wrapper });
    vi.mocked(renderMarkdownHtml).mockClear();

    rerender(list({ ...plainMessage, content: 'A *few* more things.' }));

    expect(vi.mocked(renderMarkdownHtml).mock.calls.map(([markdown]) => markdown)).toEqual(['A *few* more things.']);
  });
});

describe('Chat generative UI widgets', () => {
  const widgetContent = 'Pick one.\n\n```omnix-ui\n{"type":"choices","options":[{"label":"Compare with MSFT"},{"label":"Show the trend"}]}\n```\n\n```omnix-ui\n{"type":"form","template":"Backtest {symbol}","fields":[{"name":"symbol","kind":"select","options":["AAPL","MSFT"]}]}\n```';
  const widgetUi = {
    version: 1,
    compiler_version: 'gui-compiler-1',
    compiled_at: '2026-10-11T00:00:00Z',
    segments: [{ kind: 'markdown', start: 0, end: 11 }, { kind: 'block', id: 'b1', text: 'Options: Compare with MSFT; Show the trend' }, { kind: 'block', id: 'b2', text: 'Form: symbol (select: AAPL, MSFT)' }],
    blocks: {
      b1: { type: 'choices', id: 'b1', v: 1, options: [{ label: 'Compare with MSFT' }, { label: 'Show the trend' }], provenance: 'model', bindings: [] },
      b2: { type: 'form', id: 'b2', v: 1, template: 'Backtest {symbol}', fields: [{ name: 'symbol', label: 'symbol', kind: 'select', required: false, options: ['AAPL', 'MSFT'] }], provenance: 'model', bindings: [] },
    },
    text: 'Pick one.\n\nOptions: Compare with MSFT; Show the trend\n\nForm: symbol (select: AAPL, MSFT)',
    speech: 'Pick one.',
    diagnostics: [],
  };
  const widgetSession = {
    ...session,
    id: 'chat:widgets',
    message_count: 2,
    messages: [
      { id: 'msg:w-user', role: 'user', content: 'What next?', created_at: '2026-06-14T00:00:01Z' },
      { id: 'msg:w-reply', role: 'assistant', content: widgetContent, created_at: '2026-06-14T00:00:02Z', metadata: { ui: widgetUi } },
    ],
  };
  const posts: Array<{ path: string; body: Record<string, unknown> }> = [];
  // jsdom has no layout: the transcript's stick-to-latest scroll is a no-op here.
  beforeEach(() => {
    Element.prototype.scrollIntoView = vi.fn();
  });

  function respondWithWidgets(input: RequestInfo | URL, init?: RequestInit): Response {
    const path = new URL(String(input), 'http://localhost').pathname;
    if (init?.method === 'POST' && path.endsWith('/messages')) {
      const body = JSON.parse(String(init.body)) as Record<string, unknown>;
      posts.push({ path, body });
      return Response.json({
        session: widgetSession,
        user_message: { id: 'msg:sent', role: 'user', content: body.content, created_at: '2026-06-14T00:00:03Z', metadata: {} },
        job: { id: 'job:1', status: 'queued', module: 'chatbot', type: 'chat.generate', created_at: '2026-06-14T00:00:03Z', updated_at: '2026-06-14T00:00:03Z' },
        generation_status: 'queued',
      });
    }
    if (path === '/api/chat/sessions') return Response.json({ sessions: [widgetSession] });
    if (path === '/api/chat/sessions/chat%3Awidgets') return Response.json(widgetSession);
    return respond(input);
  }

  it('sends exactly the label of a clicked choice, with its action reference', async () => {
    posts.length = 0;
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => respondWithWidgets(input, init)));
    renderWorkspace();

    fireEvent.click(await screen.findByRole('button', { name: 'Show the trend' }));

    await vi.waitFor(() => expect(posts).toHaveLength(1));
    expect(posts[0].body.content).toBe('Show the trend');
    expect(posts[0].body.ui_action).toEqual({ source_message_id: 'msg:w-reply', block_id: 'b1', action: 'choose', option_index: 1 });
  });

  it('fills the composer from a form and sends nothing until the user does', async () => {
    posts.length = 0;
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => respondWithWidgets(input, init)));
    renderWorkspace();

    fireEvent.change(await screen.findByLabelText('symbol'), { target: { value: 'MSFT' } });
    fireEvent.click(screen.getByRole('button', { name: 'Fill message' }));

    expect(screen.getByRole('textbox', { name: 'Message' })).toHaveValue('Backtest MSFT');
    expect(posts).toHaveLength(0);
  });
});
