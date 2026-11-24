import { afterEach, describe, expect, it, vi } from 'vitest';
import { researchPodcastTopic, withResearchNotes } from './podcastResearch';

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('podcast research', () => {
  it('posts the trimmed title and brief to story\'s research route', async () => {
    const fetchMock = vi.fn(async () => Response.json({ status: 'empty', message: 'Nothing.', query: '', notes: '', sources: [] }));
    vi.stubGlobal('fetch', fetchMock);
    await expect(researchPodcastTopic('  Local AI ', ' At home ')).resolves.toMatchObject({ status: 'empty' });
    const [input, init] = fetchMock.mock.calls[0] as unknown as [RequestInfo | URL, RequestInit | undefined];
    expect(new URL(String(input), 'http://localhost').pathname).toBe('/api/podcast/research');
    expect(init?.method).toBe('POST');
    expect(JSON.parse(String(init?.body))).toEqual({ title: 'Local AI', brief: 'At home' });
  });

  it('keeps the producer\'s notes and adds the research after them', () => {
    expect(withResearchNotes('', 'Web research')).toBe('Web research');
    expect(withResearchNotes('  \n', 'Web research')).toBe('Web research');
    expect(withResearchNotes(' Mine. ', 'Web research')).toBe('Mine.\n\nWeb research');
  });
});
