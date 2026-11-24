import { afterEach, describe, expect, it, vi } from 'vitest';
import type { JobRecord } from '../../api/client';
import { episodeFrom, episodeTranscript, listPodcastEpisodes } from './podcastEpisodes';

function job(fields: Partial<JobRecord> & { id: string }): JobRecord {
  return {
    module: 'podcast', type: 'tts.multi_speaker_synthesize', status: 'completed', resource_class: 'gpu:tts', priority: 0,
    input_payload: { title: `Episode ${fields.id}`, format: 'interview', script_speakers: [{ name: 'Host', count: 3 }] },
    stages: [], output_refs: [{ type: 'audio', asset_id: `audio:${fields.id}`, audio_url: `/api/assets/audio:${fields.id}/file`, duration: 61 }],
    created_at: '2026-11-24T00:00:00Z', updated_at: '2026-11-24T00:00:00Z',
    ...fields,
  } as JobRecord;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('podcast library', () => {
  it('reads an episode from a finished final render', () => {
    expect(episodeFrom(job({ id: 'a' }))).toEqual({
      jobId: 'a', assetId: 'audio:a', title: 'Episode a', createdAt: '2026-11-24T00:00:00Z', durationSeconds: 61,
      format: 'interview', speakers: ['Host'], audioUrl: '/api/assets/audio:a/file',
    });
  });

  it('leaves out previews, unfinished renders, other modules and renders without audio', () => {
    expect(episodeFrom(job({ id: 'b', type: 'tts.synthesize' }))).toBeNull();
    expect(episodeFrom(job({ id: 'c', status: 'running' }))).toBeNull();
    expect(episodeFrom(job({ id: 'd', module: 'voice' }))).toBeNull();
    expect(episodeFrom(job({ id: 'e', output_refs: [{ type: 'audio', title: 'no audio' }] }))).toBeNull();
  });

  it('follows the jobs list page by page', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const cursor = new URL(String(input), 'http://localhost').searchParams.get('cursor');
      return Response.json(cursor
        ? { jobs: [job({ id: 'old' })], has_more: false, next_cursor: null }
        : { jobs: [job({ id: 'new' }), job({ id: 'preview', type: 'tts.synthesize' })], has_more: true, next_cursor: 'page-2' });
    });
    vi.stubGlobal('fetch', fetchMock);
    expect((await listPodcastEpisodes()).map((episode) => episode.jobId)).toEqual(['new', 'old']);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('reads the transcript from the whole job, spread over the episode', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => Response.json(job({
      id: 'a',
      input_payload: { script_segments: [{ index: 0, speaker: 'Host', text: 'Hello.' }, { index: 1, speaker: 'Guest', text: 'Hi.' }, { index: 2, speaker: 'Host', text: '' }] },
    }))));
    const episode = episodeFrom(job({ id: 'a' }));
    expect(await episodeTranscript(episode!)).toEqual({ rows: [
      { timestamp: '00:00', speaker: 'Host', text: 'Hello.' },
      { timestamp: '00:30', speaker: 'Guest', text: 'Hi.' },
    ], timeline: [] });
  });

  it('times the transcript by the render\'s timeline when it has one', async () => {
    const timed = job({ id: 'a', input_payload: { script_segments: [{ index: 0, speaker: 'Host', text: 'Hello.' }, { index: 1, speaker: 'Guest', text: 'Hi.' }] } });
    const ref = (timed.output_refs as Array<Record<string, unknown>>)[0];
    ref.timeline = [{ segment: 0, start: 2.5, end: 9 }, { segment: 1, start: 75, end: 80 }];
    vi.stubGlobal('fetch', vi.fn(async () => Response.json(timed)));
    const playback = await episodeTranscript(episodeFrom(job({ id: 'a' }))!);
    expect(playback.timeline).toEqual([{ line: 0, start: 2.5 }, { line: 1, start: 75 }]);
    expect(playback.rows.map((row) => row.timestamp)).toEqual(['00:02', '01:15']);
  });
});
