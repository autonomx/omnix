import { afterEach, describe, expect, it, vi } from 'vitest';
import { stubGateway } from '../../test/renderWithProviders';
import { parseScriptSegments, requestPodcastScript, scriptSummary } from './podcastScript';

afterEach(() => {
  vi.unstubAllGlobals();
});

const CAST = ['Jinx', 'Abhishek'];
const request = {
  title: 'AI at home',
  brief: 'What changes when assistants run locally?',
  audience: 'Builders',
  format: 'debate',
  tone: 'Playful',
  durationMinutes: 5,
  speakers: [
    { name: 'Jinx', personality: 'Chaotic', speakingStyle: 'Fast' },
    { name: 'Abhishek', role: 'Engineer', goal: 'Explain the tradeoffs' },
  ],
};

/** A posted job as these tests read it. */
type PostedJob = { input_payload: Record<string, unknown> & { speaker_profiles: Array<Record<string, unknown>> } };

function job(fields: Record<string, unknown>) {
  return { id: 'job:script', module: 'podcast', type: 'podcast.generate', resource_class: 'gpu:llm', status: 'queued', input_payload: {}, stages: [], output_refs: [], created_at: '2026-11-24T00:00:00Z', updated_at: '2026-11-24T00:00:00Z', priority: 1, ...fields };
}

describe('requestPodcastScript', () => {
  it('writes the script in a podcast.generate job on the podcast model, and reads its lines', async () => {
    const posted: PostedJob[] = [];
    let polls = 0;
    stubGateway({
      'GET /api/settings/profile': () => ({ settings: { settings_control_center: { podcast: { providerId: 'llm:lmstudio', modelId: 'llm:lmstudio:qwen' } } } }),
      'POST /api/jobs': ({ body }) => {
        posted.push(body as PostedJob);
        return job({});
      },
      'GET /api/jobs/job%3Ascript': () => {
        polls += 1;
        return polls < 2 ? job({ status: 'running' }) : job({
          status: 'completed',
          output_refs: [{
            type: 'podcast_script',
            content: '```json\n{"segments":[{"speaker":"jinx","text":"Hi!"},{"speaker":"Abhishek","text":"Hello.","pause_before_ms":150,"delivery_instruction":"warmly"}]}\n```',
            resolved_model: 'qwen3-27b',
            script_quality: { lines: 2, words: 2, minutes: 0, target_minutes: 5, speaker_share: { Jinx: 50, Abhishek: 50 } },
          }],
        });
      },
    });

    await expect(requestPodcastScript({ ...request, sources: '  Survey: 61% run models locally.  ' }, { pollMs: 1 })).resolves.toEqual({
      segments: [
        { index: 0, speaker: 'Jinx', text: 'Hi!' },
        { index: 1, speaker: 'Abhishek', text: 'Hello.', pause_before_ms: 150, delivery_instruction: 'warmly' },
      ],
      model: 'qwen3-27b',
      quality: { lines: 2, words: 2, minutes: 0, target_minutes: 5, speaker_share: { Jinx: 50, Abhishek: 50 } },
    });
    expect(posted).toHaveLength(1);
    expect(posted[0]).toMatchObject({
      module: 'podcast',
      type: 'podcast.generate',
      resource_class: 'gpu:llm',
      input_payload: {
        title: 'AI at home', audience: 'Builders', format: 'debate', tone: 'Playful', duration_minutes: 5, speakers: CAST,
        provider_id: 'llm:lmstudio', model_id: 'llm:lmstudio:qwen', sources: 'Survey: 61% run models locally.',
      },
    });
    expect(posted[0].input_payload.speaker_profiles[1]).toMatchObject({ name: 'Abhishek', role: 'Engineer', goal: 'Explain the tradeoffs' });
  });

  it('fails with the job\'s reason, and when the script has no speaker lines', async () => {
    stubGateway({ 'POST /api/jobs': () => job({ status: 'failed', error: { code: 'story_job_failed', message: 'LLM provider is unavailable' } }) });
    await expect(requestPodcastScript(request, { pollMs: 1 })).rejects.toThrow('The podcast script could not be written: LLM provider is unavailable');

    stubGateway({ 'POST /api/jobs': () => job({ status: 'completed', output_refs: [{ type: 'podcast_script', content: 'Sorry, I cannot help with that.' }] }) });
    await expect(requestPodcastScript(request, { pollMs: 1 })).rejects.toThrow(/without speaker lines/);
  });

  it('passes on which part of a long episode is being written', async () => {
    const steps = ['Planning the episode', 'Writing part 1 of 2', 'Writing part 1 of 2', 'Writing part 2 of 2'];
    let polls = 0;
    stubGateway({
      'POST /api/jobs': () => job({}),
      'GET /api/jobs/job%3Ascript': () => {
        polls += 1;
        return polls <= steps.length
          ? job({ status: 'running', progress: { current: polls - 1, total: 3, message: steps[polls - 1] } })
          : job({ status: 'completed', output_refs: [{ type: 'podcast_script', content: '{"segments":[{"speaker":"Jinx","text":"Hi!"}]}' }] });
      },
    });
    const shown: string[] = [];
    await requestPodcastScript({ ...request, durationMinutes: 15 }, { pollMs: 1, onProgress: (step) => shown.push(step) });
    expect(shown).toEqual(['Planning the episode', 'Writing part 1 of 2', 'Writing part 2 of 2']);
  });

  it('sends no source notes when there are none', async () => {
    const posted: PostedJob[] = [];
    stubGateway({ 'POST /api/jobs': ({ body }) => {
      posted.push(body as PostedJob);
      return job({ status: 'completed', output_refs: [{ type: 'podcast_script', content: '{"segments":[{"speaker":"Jinx","text":"Hi!"}]}' }] });
    } });
    const script = await requestPodcastScript({ ...request, sources: '   ' }, { pollMs: 1 });
    expect(posted[0].input_payload).not.toHaveProperty('sources');
    expect(script).toMatchObject({ model: '', quality: null });
  });

  it('gives up waiting with a message rather than a stand-in script, and stops the job it gave up on', async () => {
    const canceled: unknown[] = [];
    stubGateway({
      'POST /api/jobs': () => job({}),
      'GET /api/jobs/job%3Ascript': () => job({ status: 'running' }),
      'POST /api/jobs/job%3Ascript/cancel': ({ body }) => { canceled.push(body); return job({ status: 'canceled' }); },
    });
    await expect(requestPodcastScript(request, { waitMs: 5, pollMs: 1 })).rejects.toThrow(/took longer than expected/);
    await vi.waitFor(() => expect(canceled).toEqual([{ reason: 'The studio stopped waiting for this script.' }]));
  });
});

describe('parseScriptSegments', () => {
  it('keeps the complete lines of a script cut off mid-way', () => {
    const cut = '{"segments": [{"speaker": "Jinx", "text": "Boom, \\"welcome\\"!"}, {"speaker": "Abhishek", "text": "Thanks."}, {"speaker": "Jinx", "text": "So the';
    expect(parseScriptSegments(cut, CAST)).toEqual([
      { index: 0, speaker: 'Jinx', text: 'Boom, "welcome"!' },
      { index: 1, speaker: 'Abhishek', text: 'Thanks.' },
    ]);
  });

  it('reads "Name: line" rows of the cast only, and drops a line said word for word before', () => {
    const script = 'Title: AI at home\n**Jinx:** Welcome!\nAbhishek: Local models change privacy.\nJINX: Welcome!\nNarrator: (music)\n';
    expect(parseScriptSegments(script, CAST)).toEqual([
      { index: 0, speaker: 'Jinx', text: 'Welcome!' },
      { index: 1, speaker: 'Abhishek', text: 'Local models change privacy.' },
    ]);
  });

  it('reads a bare list and other field names', () => {
    expect(parseScriptSegments('[{"name": "Abhishek", "line": "One."}, {"speaker": "Jinx", "content": "Two."}]', CAST)).toEqual([
      { index: 0, speaker: 'Abhishek', text: 'One.' },
      { index: 1, speaker: 'Jinx', text: 'Two.' },
    ]);
  });
});

describe('scriptSummary', () => {
  it('says how long the script came out, what was fixed, who spoke and which model wrote it', () => {
    expect(scriptSummary({ words: 1480, minutes: 9.9, target_minutes: 10, edited: 2, cut: 1, near_repeats: 1, speaker_share: { Host: 52, Guest: 48 } }, 'qwen3'))
      .toBe(' (1,480 words, about 10 of 10 minutes; 3 repeated or overlong lines fixed; 1 near-repeat left; Host 52%, Guest 48%; written by qwen3)');
    expect(scriptSummary(null, '')).toBe('');
    expect(scriptSummary({ words: 40, speaker_share: { Host: 100 } }, '')).toBe(' (40 words)');
  });
});
