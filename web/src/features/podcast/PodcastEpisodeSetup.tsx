import type { Dispatch, SetStateAction } from 'react';
import { sourceNotesLimit, withResearchNotes } from './podcastResearch';
import { PodcastResearchRow } from './PodcastResearchRow';
import type { PodcastFormat } from './types';

/** Step 1 of the podcast studio: what the episode is about and how it should sound. */
export type EpisodeSettings = {
  title: string;
  brief: string;
  audience: string;
  duration: string;
  tone: string;
  language: string;
  format: PodcastFormat;
  generationStyle: string;
  sources: string;
  bookends: boolean;
  roomTone: boolean;
};

export const defaultEpisode: EpisodeSettings = {
  title: 'The Future of AI in Everyday Life',
  brief: 'Explore how artificial intelligence is shaping our daily lives, transforming work and productivity, inspiring creativity, influencing relationships, and augmenting decision-making. We will discuss opportunities, risks, and what comes next.',
  audience: 'Software Engineers',
  duration: '20 min',
  tone: 'Professional',
  language: 'English (US)',
  format: 'debate',
  generationStyle: 'automatic',
  sources: '',
  bookends: false,
  roomTone: false,
};

const durations = ['2 min', '5 min', '10 min', '15 min', '20 min', '30 min', '45 min', '60 min'];
export const formats: Array<{ id: PodcastFormat; label: string; description: string }> = [
  { id: 'debate', label: 'Debate', description: 'Two or more opposing sides' },
  { id: 'interview', label: 'Interview', description: 'Host interviews guests' },
  { id: 'speech', label: 'Speech', description: 'Solo host presentation' },
];

export function PodcastEpisodeSetup({ episode, setEpisode, onNewPodcast, running = false }: {
  episode: EpisodeSettings;
  setEpisode: Dispatch<SetStateAction<EpisodeSettings>>;
  onNewPodcast: () => void;
  /** A run is going: a new podcast would clear what it is still filling in (Stop first). */
  running?: boolean;
}) {
  const { title, brief, audience, duration, tone, language, format, generationStyle, sources, bookends, roomTone } = episode;
  const set = <K extends keyof EpisodeSettings>(key: K, value: EpisodeSettings[K]) => setEpisode((current) => ({ ...current, [key]: value }));
  return (
    <article className="podcast-card episode-setup-card">
      <div className="card-heading-row"><h3>1. Episode setup</h3><button className="ghost-button compact" type="button" onClick={onNewPodcast} disabled={running} title={running ? 'Stop the run first' : undefined}>New podcast</button></div>
      <div className="episode-setup-grid">
        <div className="podcast-field-stack">
          <label>Topic / Episode title<input value={title} onChange={(event) => set('title', event.target.value)} /></label>
          <label>Episode brief<textarea rows={5} value={brief} onChange={(event) => set('brief', event.target.value)} /><small>{brief.length}/2000</small></label>
          <label>Source notes<textarea rows={4} value={sources} placeholder="Facts, figures and quotes for the hosts to draw on. The script will not invent statistics." onChange={(event) => set('sources', event.target.value)} /><small>{sources.length}/{sourceNotesLimit}{sources.length > sourceNotesLimit ? ` (the script reads the first ${sourceNotesLimit})` : ''}</small></label>
          {/* Added to the notes as they are now: the producer may have typed while the search ran. */}
          <PodcastResearchRow title={title} brief={brief} onNotes={(notes) => setEpisode((current) => ({ ...current, sources: withResearchNotes(current.sources, notes) }))} />
          <label>Audience<select value={audience} onChange={(event) => set('audience', event.target.value)}><option>Software Engineers</option><option>General Public</option><option>Executives</option><option>Students</option><option>Experts</option></select></label>
        </div>
        <div className="podcast-config-stack">
          <span className="podcast-label">Podcast format</span>
          <div className="format-card-grid">{formats.map((option) => <button key={option.id} type="button" className={option.id === format ? 'selected' : undefined} onClick={() => set('format', option.id)}><strong>{option.label}</strong><small>{option.description}</small></button>)}</div>
          <div className="podcast-select-grid">
            <label>Duration<select value={duration} onChange={(event) => set('duration', event.target.value)}>{durations.map((option) => <option key={option}>{option}</option>)}</select></label>
            <label>Tone<select value={tone} onChange={(event) => set('tone', event.target.value)}><option>Professional</option><option>Conversational</option><option>Humorous</option></select></label>
            <label>Language<select value={language} onChange={(event) => set('language', event.target.value)}><option>English (US)</option><option>English (UK)</option></select></label>
          </div>
          <label>Generation Style<select value={generationStyle} onChange={(event) => set('generationStyle', event.target.value)}><option value="automatic">Automatic</option><option value="guided">Guided</option></select></label>
          <div className="podcast-option-group" role="group" aria-label="Sound">
            <span className="podcast-label">Sound</span>
            <label className="podcast-option-toggle"><input type="checkbox" checked={bookends} onChange={(event) => set('bookends', event.target.checked)} /><span><strong>Intro and outro sting</strong><small>A short chime opens and closes the final render</small></span></label>
            <label className="podcast-option-toggle"><input type="checkbox" checked={roomTone} onChange={(event) => set('roomTone', event.target.checked)} /><span><strong>Room tone</strong><small>A faint room sound under the voices, so pauses are not dead silence</small></span></label>
          </div>
        </div>
      </div>
    </article>
  );
}
