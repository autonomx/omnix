import { afterEach, describe, expect, it, vi } from 'vitest';

type AssistantContextTestWindow = Window & typeof globalThis & {
  __omnixAssistantContextInitialized?: boolean;
};

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  document.body.innerHTML = '';
  delete (window as AssistantContextTestWindow).__omnixAssistantContextInitialized;
});

describe('assistant context live-chat critical path', () => {
  it('mounts a plus menu that selects the same research modes used by chat requests', async () => {
    vi.resetModules();
    delete (window as AssistantContextTestWindow).__omnixAssistantContextInitialized;
    document.body.innerHTML = '<form class="assistant-composer"><div class="assistant-composer-controls"></div><label class="assistant-message-input"><textarea></textarea></label><div class="assistant-composer-actions"></div></form><div class="assistant-audio-devices"></div>';
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(new Response(JSON.stringify({ settings: {} }), { status: 200 }))) as unknown as typeof fetch);

    await import('./assistant-context-controller');

    const addButton = document.querySelector<HTMLButtonElement>('.assistant-context-add-button');
    const menu = document.querySelector<HTMLElement>('.assistant-context-tool-menu');
    expect(addButton).toBeTruthy();
    expect(menu).toBeTruthy();
    expect(menu?.hidden).toBe(true);
    expect(menu?.querySelector('[data-omnix-context-tool-desktop]')).toBeTruthy();

    addButton?.click();
    expect(menu?.hidden).toBe(false);
    menu?.querySelector<HTMLButtonElement>('[data-omnix-context-tool-mode="quick"]')?.click();

    expect(menu?.hidden).toBe(true);
    expect(document.querySelector<HTMLSelectElement>('select[aria-label="Web research mode"]')?.value).toBe('quick');
    expect(document.querySelector('.assistant-context-tool-summary')?.textContent).toContain('Quick search');
  });

  it('opens the chat response before deferred research-mode persistence completes', async () => {
    vi.resetModules();
    delete (window as AssistantContextTestWindow).__omnixAssistantContextInitialized;
    document.body.innerHTML = '<main></main>';

    let resolvePersistence: (response: Response) => void = () => undefined;
    const persistenceResponse = new Promise<Response>((resolve) => {
      resolvePersistence = resolve;
    });
    const requestPaths: string[] = [];
    const fetchMock = vi.fn((input: RequestInfo | URL): Promise<Response> => {
      const raw = typeof input === 'string' || input instanceof URL ? input.toString() : input.url;
      const path = new URL(raw, window.location.origin).pathname;
      requestPaths.push(path);
      if (path === '/api/settings') {
        return Promise.resolve(new Response(JSON.stringify({
          settings: {
            settings_control_center: {
              assistant: { researchDefaultMode: 'disabled' },
            },
          },
        }), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        }));
      }
      if (path === '/api/chat/sessions/s1/messages/stream') {
        return Promise.resolve(new Response('data: {"type":"done"}\n\n', {
          status: 200,
          headers: { 'content-type': 'text/event-stream' },
        }));
      }
      if (path === '/api/chat/sessions/s1/research-mode') return persistenceResponse;
      return Promise.resolve(new Response(null, { status: 404 }));
    }) as unknown as typeof fetch;
    vi.stubGlobal('fetch', fetchMock);

    const module = await import('./assistant-context-controller');
    module.initializeAssistantContextController(document);
    await Promise.resolve();

    const responsePromise = window.fetch('/api/chat/sessions/s1/messages/stream', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ content: 'hello' }),
    });
    const response = await Promise.race([
      responsePromise,
      new Promise<never>((_, reject) => {
        window.setTimeout(() => reject(new Error('chat response was blocked by persistence')), 100);
      }),
    ]);

    expect(response.status).toBe(200);
    await vi.waitFor(() => {
      expect(requestPaths).toContain('/api/chat/sessions/s1/research-mode');
    });
    expect(requestPaths.indexOf('/api/chat/sessions/s1/messages/stream')).toBeLessThan(
      requestPaths.indexOf('/api/chat/sessions/s1/research-mode'),
    );

    resolvePersistence(new Response(null, { status: 200 }));
  });
});
