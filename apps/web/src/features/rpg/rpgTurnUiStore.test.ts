import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  beginRpgTurnUiSubmission,
  completeRpgTurnUiSubmission,
  createRpgSubmissionId,
  getRpgTurnUiEntries,
  installRpgTurnUiFetchInterceptor,
  mergeRpgTurnUiMessages,
  refreshPathsForChangedDomains,
  resetRpgTurnUiStoreForTests,
} from './rpgTurnUiStore';

afterEach(() => {
  resetRpgTurnUiStoreForTests();
  vi.restoreAllMocks();
});

describe('rpgTurnUiStore', () => {
  it('creates stable server idempotency keys', () => {
    expect(createRpgSubmissionId()).toMatch(/^submit:[a-z0-9]+$/i);
  });

  it('shows the player command immediately and replaces the pending placeholder by interaction id', () => {
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
    expect(entries.map((entry) => entry.text)).toEqual([
      'I ask Bran how business is doing.',
      'Bran rests the polishing rag on the counter.',
      'Steady enough, though the old road has been quiet.',
    ]);
    expect(entries.every((entry) => entry.status === 'complete')).toBe(true);
    expect(entries.slice(1).every((entry) => entry.interactionId === 'interaction:1')).toBe(true);
  });

  it('adds a submission header and consumes the compact visible response', async () => {
    const fetchImpl = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      const headers = new Headers(init?.headers);
      expect(headers.get('X-Omnix-Rpg-Submission-Id')).toMatch(/^submit:/);
      return new Response(JSON.stringify({
        ok: true,
        contract_version: 'rpg_turn_response_v2',
        session_id: 'session:bran',
        interaction_id: 'interaction:2',
        visible_response: {
          narration: 'Bran glances toward the window.',
          messages: [{ kind: 'npc_dialogue', speaker: 'Bran', text: 'The road is quieter than it should be.' }],
        },
        state: { changed: true, changed_domains: ['conversation'] },
      }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    });
    installRpgTurnUiFetchInterceptor(fetchImpl as typeof fetch);

    await fetch('/api/rpg/sessions/session%3Abran/turn', {
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
  });

  it('discards optimistic entries when the client falls back from a missing foreground route', async () => {
    const fetchImpl = vi.fn(async () => new Response('not found', { status: 404 }));
    installRpgTurnUiFetchInterceptor(fetchImpl as typeof fetch);

    const response = await fetch('/api/rpg/sessions/session%3Abran/turn', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ command: 'How is business?' }),
    });

    expect(response.status).toBe(404);
    expect(getRpgTurnUiEntries('session:bran')).toEqual([]);
  });

  it('does not request heavy query refreshes for explicit conversation-only turns', () => {
    expect(refreshPathsForChangedDomains('session:bran', ['conversation'])).toEqual([]);
    expect(refreshPathsForChangedDomains('session:bran', [])).toEqual([
      '/api/rpg/sessions/session%3Abran',
    ]);
    expect(refreshPathsForChangedDomains('session:bran', ['conversation', 'inventory', 'currency'])).toEqual([
      '/api/rpg/sessions/session%3Abran',
      '/api/replay/inventory',
    ]);
    expect(refreshPathsForChangedDomains('session:bran', ['location', 'world'])).toEqual([
      '/api/rpg/sessions/session%3Abran',
      '/api/reports',
    ]);
  });

  it('deduplicates entries that later arrive through the canonical session transcript', () => {
    const merged = mergeRpgTurnUiMessages(
      [{ avatar: 'B', speaker: 'Bran', text: 'Steady enough.', tone: 'npc' }],
      [{
        id: 'interaction:1:message:0',
        sessionId: 'session:bran',
        submissionId: 'submit:one',
        interactionId: 'interaction:1',
        status: 'complete',
        avatar: 'B',
        speaker: 'Bran',
        text: 'Steady enough.',
        tone: 'npc',
      }],
    );

    expect(merged).toHaveLength(1);
  });
});
