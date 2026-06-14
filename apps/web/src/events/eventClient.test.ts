import { afterEach, describe, expect, it, vi } from 'vitest';
import { OmnixEventClient, type OmnixEventClientOptions, type OmnixEventSource } from './eventClient';

class FakeEventSource implements OmnixEventSource {
  readonly listeners = new Map<string, Set<EventListener>>();
  closed = false;

  constructor(readonly endpoint: string) {}

  addEventListener(type: string, listener: EventListener) {
    const listenersForType = this.listeners.get(type) ?? new Set<EventListener>();
    listenersForType.add(listener);
    this.listeners.set(type, listenersForType);
  }

  removeEventListener(type: string, listener: EventListener) {
    this.listeners.get(type)?.delete(listener);
  }

  close() {
    this.closed = true;
  }

  listenerCount(type: string) {
    return this.listeners.get(type)?.size ?? 0;
  }

  emitOpen() {
    this.emit('open', new Event('open'));
  }

  emitError() {
    this.emit('error', new Event('error'));
  }

  emitMessage(type: string, data: string) {
    this.emit(type, new MessageEvent(type, { data }));
  }

  private emit(type: string, event: Event) {
    for (const listener of [...(this.listeners.get(type) ?? [])]) {
      listener(event);
    }
  }
}

function createClient(options: Partial<OmnixEventClientOptions> = {}) {
  const sources: FakeEventSource[] = [];
  const client = new OmnixEventClient({
    endpoint: '/events',
    eventSourceFactory: (endpoint) => {
      const source = new FakeEventSource(endpoint);
      sources.push(source);
      return source;
    },
    initialReconnectDelayMs: 100,
    maxReconnectDelayMs: 1_000,
    reconnectJitterRatio: 0,
    ...options,
  });

  return { client, sources };
}

afterEach(() => {
  vi.useRealTimers();
});

describe('OmnixEventClient', () => {
  it('subscribes, parses named events, reports status, and closes after unsubscribe', () => {
    const { client, sources } = createClient();
    const statuses: string[] = [];
    const handler = vi.fn();

    client.subscribeStatus((status) => statuses.push(status.state));
    const unsubscribe = client.subscribe('jobs.updated', handler);

    expect(sources).toHaveLength(1);
    expect(sources[0].endpoint).toBe('/events');
    expect(sources[0].listenerCount('jobs.updated')).toBe(1);
    expect(statuses).toEqual(['idle', 'connecting']);

    sources[0].emitOpen();
    sources[0].emitMessage('jobs.updated', '{"id":"job-1","progress":0.5}');

    expect(handler).toHaveBeenCalledWith({ id: 'job-1', progress: 0.5 });
    expect(client.getStatus().state).toBe('open');

    unsubscribe();

    expect(sources[0].closed).toBe(true);
    expect(client.getStatus()).toEqual({ state: 'idle', reconnectAttempt: 0 });
  });

  it('multiplexes multiple named events over one source', () => {
    const { client, sources } = createClient();
    const jobHandler = vi.fn();
    const diagnosticsHandler = vi.fn();

    client.subscribe('jobs.updated', jobHandler);
    client.subscribe('diagnostics.updated', diagnosticsHandler);

    expect(sources).toHaveLength(1);
    expect(sources[0].listenerCount('jobs.updated')).toBe(1);
    expect(sources[0].listenerCount('diagnostics.updated')).toBe(1);

    sources[0].emitMessage('jobs.updated', '{"id":"job-2"}');
    sources[0].emitMessage('diagnostics.updated', '{"ok":true}');

    expect(jobHandler).toHaveBeenCalledWith({ id: 'job-2' });
    expect(diagnosticsHandler).toHaveBeenCalledWith({ ok: true });
  });

  it('supports multiple listeners for one named event', () => {
    const { client, sources } = createClient();
    const firstHandler = vi.fn();
    const secondHandler = vi.fn();

    const unsubscribeFirst = client.subscribe('assets.created', firstHandler);
    client.subscribe('assets.created', secondHandler);

    expect(sources[0].listenerCount('assets.created')).toBe(1);

    sources[0].emitMessage('assets.created', '{"assetId":"asset-1"}');
    unsubscribeFirst();
    sources[0].emitMessage('assets.created', '{"assetId":"asset-2"}');

    expect(firstHandler).toHaveBeenCalledTimes(1);
    expect(secondHandler).toHaveBeenCalledTimes(2);
  });

  it('reports malformed JSON without calling subscribers', () => {
    const malformedHandler = vi.fn();
    const { client, sources } = createClient({ onMalformedEvent: malformedHandler });
    const handler = vi.fn();

    client.subscribe('jobs.updated', handler);
    sources[0].emitMessage('jobs.updated', '{not-json');

    expect(handler).not.toHaveBeenCalled();
    expect(malformedHandler).toHaveBeenCalledWith(
      expect.objectContaining({
        eventName: 'jobs.updated',
        data: '{not-json',
      }),
    );
  });

  it('reconnects with backoff and rebinds named-event listeners', () => {
    vi.useFakeTimers();

    const { client, sources } = createClient();
    const handler = vi.fn();

    client.subscribe('jobs.updated', handler);
    sources[0].emitOpen();
    sources[0].emitError();

    expect(sources[0].closed).toBe(true);
    expect(client.getStatus()).toEqual({
      state: 'reconnecting',
      reconnectAttempt: 1,
      nextReconnectDelayMs: 100,
      lastError: 'error',
    });

    vi.advanceTimersByTime(99);
    expect(sources).toHaveLength(1);

    vi.advanceTimersByTime(1);
    expect(sources).toHaveLength(2);
    expect(client.getStatus().state).toBe('connecting');

    sources[1].emitOpen();
    sources[1].emitMessage('jobs.updated', '{"id":"job-3"}');

    expect(client.getStatus()).toEqual({ state: 'open', reconnectAttempt: 0 });
    expect(sources[1].listenerCount('jobs.updated')).toBe(1);
    expect(handler).toHaveBeenCalledWith({ id: 'job-3' });
  });

  it('cancels pending reconnect when closed', () => {
    vi.useFakeTimers();

    const { client, sources } = createClient();

    client.subscribe('jobs.updated', vi.fn());
    sources[0].emitError();
    client.close();
    vi.runAllTimers();

    expect(sources).toHaveLength(1);
    expect(client.getStatus()).toEqual({ state: 'closed', reconnectAttempt: 0 });
  });

  it('does not reconnect after the final event subscriber unsubscribes', () => {
    vi.useFakeTimers();

    const { client, sources } = createClient();

    const unsubscribe = client.subscribe('jobs.updated', vi.fn());
    sources[0].emitError();
    unsubscribe();
    vi.runAllTimers();

    expect(sources).toHaveLength(1);
    expect(client.getStatus()).toEqual({ state: 'idle', reconnectAttempt: 0 });
  });
});
