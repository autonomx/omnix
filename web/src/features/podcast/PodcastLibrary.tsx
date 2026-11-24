import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { downloadUrl } from '../../shared/download';
import { formats } from './PodcastEpisodeSetup';
import type { TranscriptRow } from './PodcastStudioParts';
import { clock, episodeTranscript, listPodcastEpisodes, podcastLibraryKey, type PodcastEpisode } from './podcastEpisodes';
import type { LineStart } from './podcastTimeline';

const when = (iso: string) => {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
};
const formatLabel = (id: string) => formats.find((option) => option.id === id)?.label ?? '';
const fileName = (title: string) => `${title.replace(/[\\/:*?"<>|]+/g, ' ').trim() || 'podcast'}.wav`;

/** Every finished podcast: play one in the studio player (with its transcript) or download it. */
export function PodcastLibrary({ playingJobId, disabled, onPlay }: {
  /** The episode in the player, if it came from the library. */
  playingJobId: string | null;
  /** A run is in progress: the player is the run's until it ends. */
  disabled: boolean;
  /** The episode, its transcript, and where each line plays (empty for renders that didn't report it). */
  onPlay: (episode: PodcastEpisode, rows: TranscriptRow[], timeline: LineStart[]) => void;
}) {
  const library = useQuery({ queryKey: podcastLibraryKey, queryFn: listPodcastEpisodes, retry: false, refetchOnWindowFocus: false });
  const [search, setSearch] = useState('');
  const [opening, setOpening] = useState<string | null>(null);
  const episodes = library.data ?? [];
  const needle = search.trim().toLowerCase();
  const shown = needle ? episodes.filter((episode) => `${episode.title} ${episode.speakers.join(' ')}`.toLowerCase().includes(needle)) : episodes;

  async function play(episode: PodcastEpisode) {
    setOpening(episode.jobId);
    // The audio plays even if the script can't be read; the transcript is then empty.
    const { rows, timeline } = await episodeTranscript(episode).catch(() => ({ rows: [], timeline: [] }));
    setOpening(null);
    onPlay(episode, rows, timeline);
  }

  return (
    <aside className="podcast-sidebar">
      <article className="podcast-card recent-card podcast-library-card" aria-label="Podcast library">
        <div className="card-heading-row"><h3>Library</h3><small>{library.isPending ? 'Loading...' : `${episodes.length} episode${episodes.length === 1 ? '' : 's'}`}</small></div>
        {episodes.length > 3 ? <input className="podcast-library-search" type="search" aria-label="Search the library" placeholder="Search by title or speaker" value={search} onChange={(event) => setSearch(event.target.value)} /> : null}
        {library.isError ? <p className="podcast-library-empty">The library could not be loaded.</p> : null}
        {library.isSuccess && !episodes.length ? <p className="podcast-library-empty">No finished podcasts yet. Each final render is kept here.</p> : null}
        {episodes.length && !shown.length ? <p className="podcast-library-empty">No episode matches.</p> : null}
        <ul className="podcast-library-list">
          {shown.map((episode) => {
            const playing = episode.jobId === playingJobId;
            const details = [formatLabel(episode.format), episode.speakers.length ? `${episode.speakers.length} voice${episode.speakers.length === 1 ? '' : 's'}` : '', episode.durationSeconds ? clock(episode.durationSeconds) : ''].filter(Boolean).join(' - ');
            return (
              <li key={episode.jobId} className={playing ? 'playing' : undefined}>
                <div className="podcast-library-copy">
                  <strong title={episode.title}>{episode.title}</strong>
                  <small>{details}</small>
                  <small title={episode.speakers.join(', ')}>{[when(episode.createdAt), episode.speakers.join(', ')].filter(Boolean).join(' - ')}</small>
                </div>
                <div className="podcast-library-actions">
                  <button type="button" disabled={disabled || opening !== null} aria-label={`Play ${episode.title}`} onClick={() => void play(episode)}>{opening === episode.jobId ? 'Opening...' : playing ? 'Playing' : 'Play'}</button>
                  <button type="button" aria-label={`Download ${episode.title}`} onClick={() => downloadUrl(episode.audioUrl, fileName(episode.title))}>WAV</button>
                </div>
              </li>
            );
          })}
        </ul>
      </article>
    </aside>
  );
}
