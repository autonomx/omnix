import { describe, expect, it } from 'vitest';
import type { AssistantWorkspaceEvent } from './events';
import {
  createInMemoryAssistantWorkspaceEventStore,
  createStoredAssistantWorkspaceEventStore,
  parseAssistantWorkspaceEvents,
  serializeAssistantWorkspaceEvents,
} from './event-store';

function userEvent(id: string, workspaceId = 'workspace-1', sessionId = 'session-1'): AssistantWorkspaceEvent {
  return {
    id,
    type: 'user_message',
    workspaceId,
    sessionId,
    payload: {
      turn: {
        id: `${id}-turn`,
        sessionId,
        role: 'user',
        content: [{ kind: 'text', text: 'Hello' }],
        metadata: {},
        createdAt: '2026-01-01T00:00:00.000Z',
      },
    },
    createdAt: '2026-01-01T00:00:00.000Z',
  };
}

describe('assistant workspace event stores', () => {
  it('appends, filters, and clones in-memory events', () => {
    const store = createInMemoryAssistantWorkspaceEventStore();
    const event = userEvent('event-1');

    store.append(event);
    if (event.type !== 'user_message') throw new Error('expected user event');
    event.payload.turn.content = [];

    const stored = store.get('event-1');
    if (stored?.type !== 'user_message') throw new Error('expected stored user event');

    expect(stored.payload.turn.content).toHaveLength(1);
    expect(store.list({ workspaceId: 'workspace-1', type: 'user_message' })).toHaveLength(1);
    expect(store.list({ sessionId: 'missing' })).toEqual([]);
  });

  it('persists events to injected storage', () => {
    const values = new Map<string, string>();
    const storage = {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => values.set(key, value),
      removeItem: (key: string) => values.delete(key),
    };

    const store = createStoredAssistantWorkspaceEventStore(storage, 'events');
    store.append(userEvent('event-1'));

    const reloaded = createStoredAssistantWorkspaceEventStore(storage, 'events');
    expect(reloaded.list({ sessionId: 'session-1' }).map((event) => event.id)).toEqual(['event-1']);

    reloaded.clear();
    expect(storage.getItem('events')).toBeNull();
  });

  it('ignores invalid serialized event entries', () => {
    const valid = userEvent('event-1');
    const serialized = JSON.stringify([valid, { id: 'bad', type: 'unknown', payload: {} }]);

    expect(parseAssistantWorkspaceEvents(serialized)).toHaveLength(1);
    expect(parseAssistantWorkspaceEvents('not json')).toEqual([]);
    expect(serializeAssistantWorkspaceEvents([valid])).toContain('event-1');
  });
});
