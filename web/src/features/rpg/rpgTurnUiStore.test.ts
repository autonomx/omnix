import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  getRpgTurnDiagnostics,
  markRpgTurnReactCommitted,
  markRpgTurnVisible,
} from './rpgTurnDiagnostics';
import {
  beginRpgTurnUiSubmission,
  completeRpgTurnUiSubmission,
  createRpgSubmissionId,
  getRpgTurnUiEntries,
  installRpgTurnUiFetchInterceptor,
  mergeRpgTurnUiMessages,
  refreshPathsForChangedDomains,
  resetRpgTurnUiStoreForTests,
  storyMessageIdentity,
  turnFailureMessage,
} from './rpgTurnUiStore';
import { pipelineFetch } from '../../api/fetchPipeline';
import { latestRpgTurnOffers } from './rpgTurnOffers';

afterEach(() => {
  resetRpgTurnUiStoreForTests();
  vi.restoreAllMocks();
});

describe('rpgTurnUiStore', () => {
  it('creates stable server idempotency keys', () => {
    expect(createRpgSubmissionId()).toMatch(/^submit:[a-z0-9]+$/i);
  });

  it('does not truncate durable history to the latest ten messages', () => {
    const baseMessages = Array.from({ length: 24 }, (_, index) => ({
      id: `interaction:${index + 1}:player`,
      interactionId: `interaction:${index + 1}`,
      avatar: 'A',
      speaker: 'Alyndra (You)',
      text: `Turn ${index + 1}`,
      tone: 'player' as const,
    }));

    const merged = mergeRpgTurnUiMessages(baseMessages, [{
      id: 'interaction:25:player',
      sessionId: 'session:history',
      submissionId: 'submit:25',
      interactionId: 'interaction:25',
      status: 'complete',
      avatar: 'A',
      speaker: 'Alyndra (You)',
      text: 'Turn 25',
      tone: 'player',
      messageKind: 'player',
      messageIndex: 0,
    }]);

    expect(merged).toHaveLength(24);
    expect(merged[0].text).toBe('Turn 1');
    expect(merged[23].text).toBe('Turn 25');
  });

  it('shows the player command immediately and rekeys the completed turn by interaction id', () => {
    beginRpgTurnUiSubmission({
      sessionId: 'session:bran',
      submissionId: 'submit:one',
      command: 'I ask Bran how business is doing.',
    });

    expect(getRpgTurnUiEntries('session:bran').map((entry) => entry.text)).toEqual([
      'I ask Bran how business is doing.',
      'Considering the scene…',
    ]);

    completeRpgTurnUiSubmission({
      sessionId: 'session:bran',
      submissionId: 'submit:one',
      payload: {
        ok: true,
        contract_version: 'rpg_turn_response_v2',
        interaction_id: 'interaction:1',
        visible_response: {
          narration: 'Bran rests the polishing rag on the counter.',
          messages: [
            {
              kind: 'npc_dialogue',
              speaker_id: 'npc:bran',
              speaker: 'Bran',
              text: 'Steady enough, though the old road has been quiet.',
            },
          ],
        },
      },
    });

    const entries = getRpgTurnUiEntries('session:bran');
    expect(entries.map((entry) => entry.id)).toEqual([
      'interaction:1:player',
      'interaction:1:narration',
      'interaction:1:message:0',
    ]);
    expect(entries.map((entry) => entry.text)).toEqual([
      'I ask Bran how business is doing.',
      'Bran rests the polishing rag on the counter.',
      'Steady enough, though the old road has been quiet.',
    ]);
    expect(entries.every((entry) => entry.status === 'complete')).toBe(true);
    expect(entries.every((entry) => entry.interactionId === 'interaction:1')).toBe(true);
  });

  it('adds submission and client timing headers, then records browser/server diagnostics', async () => {
    const fetchImpl = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      const headers = new Headers(init?.headers);
      expect(headers.get('X-Omnix-Rpg-Submission-Id')).toMatch(/^submit:/);
      expect(headers.get('X-Omnix-Rpg-Client-Started')).toMatch(/T/);
      return new Response(JSON.stringify({
        ok: true,
        contract_version: 'rpg_turn_response_v2',
        session_id: 'session:bran',
        interaction_id: 'interaction:2',
        trace_id: 'trace:2',
        visible_response: {
          narration: 'Bran glances toward the window.',
          messages: [{ kind: 'npc_dialogue', speaker: 'Bran', text: 'The road is quieter than it should be.' }],
        },
        state: { changed: true, changed_domains: ['conversation'] },
        timing: { pipeline_before_encode_ms: 12.5 },
        performance: { attribution_percent: 98.5 },
        outcome: {
          format_version: 'rpg_turn_outcome_v1',
          kind: 'player_text',
          applied_changes: [{ type: 'turn_counted', turn_count: 2 }],
          presentation: { changed_sections: ['time', 'npcs'] },
          model_calls: { total: 1, by_kind: { provider: 1 } },
        },
      }), {
        status: 200,
        headers: {
          'Content-Type': 'application/json',
          'X-Omnix-Rpg-Trace-Id': 'trace:2',
          'X-Omnix-Rpg-Response-Bytes': '777',
          'X-Omnix-Rpg-Attribution-Pct': '98.5',
          'Server-Timing': 'rpg_0_turn_apply;dur=10.000',
        },
      });
    });
    installRpgTurnUiFetchInterceptor(fetchImpl as typeof fetch);

    await pipelineFetch('/api/rpg/sessions/session%3Abran/turn', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ command: 'How is the road?' }),
    });

    expect(fetchImpl).toHaveBeenCalledTimes(1);
    expect(getRpgTurnUiEntries('session:bran').map((entry) => entry.text)).toEqual([
      'How is the road?',
      'Bran glances toward the window.',
      'The road is quieter than it should be.',
    ]);
    const diagnostic = getRpgTurnDiagnostics('session:bran')[0];
    expect(diagnostic.traceId).toBe('trace:2');
    expect(diagnostic.interactionId).toBe('interaction:2');
    expect(diagnostic.responseBytes).toBe(777);
    expect(diagnostic.serverAttributionPercent).toBe(98.5);
    expect(diagnostic.serverPayloadTiming).toEqual({ pipeline_before_encode_ms: 12.5 });
    expect(diagnostic.changedDomains).toEqual(['conversation', 'time', 'npcs']);  // the outcome's sections too
    expect(diagnostic.serverModelCalls).toBe(1);
    expect(diagnostic.client.requestToHeadersMs).toBeGreaterThanOrEqual(0);
    expect(diagnostic.client.headersToBodyMs).toBeGreaterThanOrEqual(0);
    expect(diagnostic.client.bodyToParseMs).toBeGreaterThanOrEqual(0);

    markRpgTurnReactCommitted('session:bran', ['interaction:2']);
    markRpgTurnVisible('session:bran', ['interaction:2']);
    const completedDiagnostic = getRpgTurnDiagnostics('session:bran')[0];
    expect(completedDiagnostic.client.storeToCommitMs).toBeGreaterThanOrEqual(0);
    expect(completedDiagnostic.client.commitToVisibleMs).toBeGreaterThanOrEqual(0);
    expect(completedDiagnostic.client.requestToVisibleMs).toBeGreaterThanOrEqual(0);
  });

  it('reads a campaign afresh after any change to it, and logs an undo as a turn', async () => {
    let reads = 0;
    const fetchImpl = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      if ((init?.method ?? 'GET') === 'GET') {
        reads += 1;
        return new Response(JSON.stringify({ ok: true, session: { read: reads } }), { status: 200 });
      }
      if (String(input).endsWith('/rewind')) {
        return new Response(JSON.stringify({ contract_version: 'rpg_turn_response_v2', ok: true, interaction_id: 'interaction:9',
          visible_response: { messages: [{ speaker: 'Omnix', text: 'You undo your last turn.' }] } }), { status: 200 });
      }
      return new Response(JSON.stringify({ ok: true }), { status: 200 });
    });
    installRpgTurnUiFetchInterceptor(fetchImpl as typeof fetch);
    const read = async () => (await (await pipelineFetch('/api/rpg/sessions/session%3Abran')).json()).session.read;

    expect(await read()).toBe(1);
    expect(await read()).toBe(1); // cached
    await pipelineFetch('/api/rpg/sessions/session%3Abran/loadout', { method: 'POST', body: '{}' });
    expect(await read()).toBe(2); // a pack action changed it
    await pipelineFetch('/api/rpg/map-instances/map%3A1/tactical/move', { method: 'POST', body: '{}' });
    expect(await read()).toBe(3); // so did a grid move
    await pipelineFetch('/api/rpg/sessions/session%3Abran/rewind', { method: 'POST', body: '{}' });
    expect(getRpgTurnUiEntries('session:bran')[0]).toMatchObject({ tone: 'player', text: 'Undo my last turn' });
    expect(await read()).toBe(4);
  });

  it('discards optimistic entries when the client falls back from a missing foreground route', async () => {
    const fetchImpl = vi.fn(async () => new Response('not found', { status: 404 }));
    installRpgTurnUiFetchInterceptor(fetchImpl as typeof fetch);

    const response = await pipelineFetch('/api/rpg/sessions/session%3Abran/turn', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ command: 'How is business?' }),
    });

    expect(response.status).toBe(404);
    expect(getRpgTurnUiEntries('session:bran')).toEqual([]);
  });

  it("shows the game's question or reason when a turn is refused, not a status code", async () => {
    const fetchImpl = vi.fn(async () => new Response(
      JSON.stringify({ detail: { ok: false, error: 'dialogue_target_unresolved', clarification: 'Who are you speaking to?' } }),
      { status: 400, headers: { 'Content-Type': 'application/json' } },
    ));
    installRpgTurnUiFetchInterceptor(fetchImpl as typeof fetch);

    await pipelineFetch('/api/rpg/sessions/session%3Abran/turn', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ command: 'Talk to him' }),
    });

    const failed = getRpgTurnUiEntries('session:bran').find((entry) => entry.tone !== 'player');
    expect(failed?.status).toBe('failed');
    expect(failed?.text).toBe('Who are you speaking to?');
  });

  it('shows the narration as it is written while the turn is still running', async () => {
    let finishTurn: (response: Response) => void = () => undefined;
    const draftUrls: string[] = [];
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/turn-draft?')) {
        draftUrls.push(url);
        return new Response(JSON.stringify({ text: 'The forge rings as you arrive.', done: false, found: true }), { status: 200 });
      }
      return new Promise<Response>((resolve) => {
        finishTurn = resolve;
      });
    });
    installRpgTurnUiFetchInterceptor(fetchImpl as typeof fetch);

    const pending = pipelineFetch('/api/rpg/sessions/session%3Abran/turn', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ command: 'Go to the forge' }),
    });
    await vi.waitFor(() => {
      expect(getRpgTurnUiEntries('session:bran').find((entry) => entry.tone !== 'player')?.text)
        .toBe('The forge rings as you arrive.');
    }, { timeout: 2000 });
    expect(draftUrls[0]).toMatch(/\/api\/rpg\/sessions\/session%3Abran\/turn-draft\?submission_id=submit%3A/);

    finishTurn(new Response('not found', { status: 404 }));
    await pending;
    const polls = draftUrls.length;
    await new Promise((resolve) => setTimeout(resolve, 700));
    expect(draftUrls.length).toBe(polls); // polling stops with the turn's answer
  });

  it('follows a turn on its stream: the outcome at the commit, then the narration as it is written', async () => {
    class FakeEventSource {
      static last: FakeEventSource | null = null;
      listeners: Record<string, ((event: MessageEvent<string>) => void)[]> = {};
      closed = false;
      constructor(public url: string) {
        FakeEventSource.last = this;
      }
      addEventListener(name: string, listener: (event: MessageEvent<string>) => void) {
        (this.listeners[name] ||= []).push(listener);
      }
      emit(name: string, data: unknown) {
        for (const listener of this.listeners[name] || []) listener({ data: JSON.stringify(data) } as MessageEvent<string>);
      }
      close() {
        this.closed = true;
      }
    }
    vi.stubGlobal('EventSource', FakeEventSource);
    const sent: Headers[] = [];
    const fetchImpl = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      sent.push(new Headers(init?.headers));
      return new Response(JSON.stringify({
        ok: true, contract_version: 'rpg_turn_response_v2', session_id: 'session:bran', interaction_id: 'interaction:9',
        visible_response: { plain_text: '', status: 'pending' },
        narration: { status: 'pending', stream_path: '/api/rpg/sessions/session:bran/submissions/s/stream' },
        outcome: { presentation: { facts: [{ kind: 'coin', text: 'You pay 5 copper.', tone: 'loss' }] } },
      }), { status: 200 });
    });
    installRpgTurnUiFetchInterceptor(fetchImpl as typeof fetch);
    try {
      await pipelineFetch('/api/rpg/sessions/session%3Abran/turn', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ command: 'Buy a meal' }),
      });
      expect(sent[0].get('X-Omnix-Rpg-Turn-Stream')).toBe('1');
      const told = () => getRpgTurnUiEntries('session:bran').filter((entry) => entry.tone !== 'player');
      expect(told().map((entry) => [entry.messageKind, entry.status])).toEqual([['narration', 'pending'], ['outcome', 'complete']]);
      const source = FakeEventSource.last as FakeEventSource;
      expect(source.url).toBe('/api/rpg/sessions/session:bran/submissions/s/stream');

      source.emit('narration.delta', { text: 'Orik sets a bowl down.' });
      expect(told()[0].text).toBe('Orik sets a bowl down.');
      source.emit('narration.final', { visible_response: { narration: 'Orik sets a steaming bowl before you.' } });
      expect(told().map((entry) => [entry.text, entry.status])).toEqual([
        ['Orik sets a steaming bowl before you.', 'complete'], ['You pay 5 copper.', 'complete']]);
      expect(source.closed).toBe(true);
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it("turns a refused turn's error code into words", async () => {
    const json = (detail: unknown, status = 400) => new Response(JSON.stringify({ detail }), { status });
    expect(await turnFailureMessage(json({ error: 'target_not_found' }))).toBe('There is no one or nothing by that name here.');
    expect(await turnFailureMessage(json({ error: 'odd_case' }))).toBe('The turn could not be resolved: odd case.');
    expect(await turnFailureMessage(json({ message: 'The road is closed.' }))).toBe('The road is closed.');
    expect(await turnFailureMessage(new Response('oops', { status: 500 }))).toBe('Turn failed (500).');
  });

  it('tells the player when the storyteller is unavailable', () => {
    beginRpgTurnUiSubmission({ sessionId: 'session:outage', submissionId: 'submit:outage', command: 'look around' });
    completeRpgTurnUiSubmission({
      sessionId: 'session:outage',
      submissionId: 'submit:outage',
      payload: {
        ok: true,
        contract_version: 'rpg_turn_response_v2',
        interaction_id: 'interaction:9',
        visible_response: { narration: 'You look around the grove.' },
        notices: [{ kind: 'storyteller_unavailable', message: 'The storyteller is unavailable right now.' }],
      },
    });
    const entries = getRpgTurnUiEntries('session:outage');
    expect(entries.map((entry) => entry.text)).toEqual([
      'look around',
      'You look around the grove.',
      'The storyteller is unavailable right now.',
    ]);
    expect(entries[2].messageKind).toBe('storyteller_unavailable');
  });

  it("shows what the turn changed as the outcome card's facts", () => {
    beginRpgTurnUiSubmission({ sessionId: 'session:card', submissionId: 'submit:card', command: 'buy a potion' });
    completeRpgTurnUiSubmission({
      sessionId: 'session:card',
      submissionId: 'submit:card',
      payload: {
        ok: true,
        contract_version: 'rpg_turn_response_v2',
        interaction_id: 'interaction:10',
        visible_response: { narration: 'Brindle hands you a potion.' },
        outcome: {
          presentation: {
            facts: [
              { kind: 'coin', text: '-3 silver', tone: 'loss' },
              { kind: 'item', text: '+Healing Potion', tone: 'gain' },
            ],
          },
        } as never,
      },
    });
    const [, , card] = getRpgTurnUiEntries('session:card');
    expect(card.messageKind).toBe('outcome');
    expect(card.facts).toEqual([
      { kind: 'coin', text: '-3 silver', tone: 'loss' },
      { kind: 'item', text: '+Healing Potion', tone: 'gain' },
    ]);
    expect(card.text).toBe('-3 silver · +Healing Potion');
  });

  it("keeps the turn's suggestions and the answers to its question for the composer", () => {
    beginRpgTurnUiSubmission({ sessionId: 'session:offers', submissionId: 'submit:offers', command: 'go' });
    completeRpgTurnUiSubmission({
      sessionId: 'session:offers',
      submissionId: 'submit:offers',
      payload: {
        ok: true,
        contract_version: 'rpg_turn_response_v2',
        interaction_id: 'interaction:11',
        visible_response: { narration: 'Where do you want to go?' },
        outcome: {
          presentation: {
            suggestions: [{ label: 'Look around', command: 'look around' }],
            choices: [{ label: 'The Road', command: 'go to The Road' }],
          },
        } as never,
      },
    });
    expect(latestRpgTurnOffers('session:offers')).toEqual({
      suggestions: [{ label: 'Look around', command: 'look around' }],
      choices: [{ label: 'The Road', command: 'go to The Road' }],
    });
  });

  it('does not request heavy query refreshes for explicit conversation-only turns', () => {
    expect(refreshPathsForChangedDomains('session:bran', ['conversation'])).toEqual([
      '/api/rpg/sessions/session%3Abran',
    ]);
    expect(refreshPathsForChangedDomains('session:bran', [])).toEqual([
      '/api/rpg/sessions/session%3Abran',
    ]);
    // Inventory lives in the session payload; no separate route is cached.
    expect(refreshPathsForChangedDomains('session:bran', ['conversation', 'inventory', 'currency'])).toEqual([
      '/api/rpg/sessions/session%3Abran',
    ]);
    expect(refreshPathsForChangedDomains('session:bran', ['location', 'world'])).toEqual([
      '/api/rpg/sessions/session%3Abran',
      '/api/reports',
    ]);
  });

  it('replaces a canonical base turn using interaction identity rather than text', () => {
    const merged = mergeRpgTurnUiMessages(
      [{
        id: 'interaction:1:response',
        interactionId: 'interaction:1',
        avatar: 'B',
        speaker: 'Bran',
        text: 'A combined persisted response.',
        tone: 'npc',
      }],
      [{
        id: 'interaction:1:message:0',
        sessionId: 'session:bran',
        submissionId: 'submit:one',
        interactionId: 'interaction:1',
        status: 'complete',
        avatar: 'B',
        speaker: 'Bran',
        text: 'A different incremental response.',
        tone: 'npc',
      }],
    );

    expect(merged).toHaveLength(1);
    expect(merged[0].text).toBe('A different incremental response.');
  });

  it('preserves identical wording from distinct interaction ids', () => {
    const merged = mergeRpgTurnUiMessages([], [
      {
        id: 'interaction:1:message:0',
        sessionId: 'session:bran',
        submissionId: 'submit:one',
        interactionId: 'interaction:1',
        status: 'complete',
        avatar: 'B',
        speaker: 'Bran',
        text: 'Steady enough.',
        tone: 'npc',
      },
      {
        id: 'interaction:2:message:0',
        sessionId: 'session:bran',
        submissionId: 'submit:two',
        interactionId: 'interaction:2',
        status: 'complete',
        avatar: 'B',
        speaker: 'Bran',
        text: 'Steady enough.',
        tone: 'npc',
      },
    ]);

    expect(merged).toHaveLength(2);
    expect(storyMessageIdentity(merged[0], 0)).toBe('interaction:1:message:0');
    expect(storyMessageIdentity(merged[1], 1)).toBe('interaction:2:message:0');
  });
});
