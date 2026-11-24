/** The podcast studio's display pieces: they show what the workspace holds and hand clicks back. */
import { useEffect, useRef } from 'react';
import { runPercent, type RunProgress } from './podcastProgress';

export function PodcastStudioHeader({ label }: { label: string }) {
  return (
    <header className="podcast-studio-header">
      <div>
        <p className="eyebrow">Conversation engine</p>
        <h2 id="module-title">{label}</h2>
        <p>Create a real LLM-generated podcast script, stitch live preview turns into one growing stream, then keep one final render for playback and download.</p>
      </div>
      <code>/podcast-renderer</code>
    </header>
  );
}

export type TranscriptRow = { timestamp: string; speaker: string; text: string };

/** The script, with the line being heard highlighted and kept in view (owner request 2026-11-24: follow along). */
export function PodcastTranscript({ rows, activeIndex = null }: { rows: TranscriptRow[]; activeIndex?: number | null }) {
  const boxRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    const box = boxRef.current;
    const line = activeIndex === null ? null : box?.querySelector<HTMLElement>('p.active');
    if (!box || !line) return;
    // Scroll the transcript box only, never the page, and only when the line is out of view.
    const top = line.getBoundingClientRect().top - box.getBoundingClientRect().top + box.scrollTop;
    if (top < box.scrollTop || top + line.offsetHeight > box.scrollTop + box.clientHeight) box.scrollTop = Math.max(0, top - box.clientHeight / 3);
  }, [activeIndex]);
  return (
    <section className="live-transcript-section">
      <div className="card-heading-row"><h4>Transcript</h4><small>{rows.length ? `${rows.length} line${rows.length === 1 ? '' : 's'}` : 'Waiting for script'}</small></div>
      <div className="live-transcript" ref={boxRef}>
        {rows.length ? rows.map((line, index) => <p key={`${line.timestamp}-${index}`} className={index === activeIndex ? 'active' : undefined} aria-current={index === activeIndex ? 'true' : undefined}><time>{line.timestamp}</time><b title={line.speaker}>{String(line.speaker).slice(0, 18)}</b><span>{line.text}</span></p>) : <div className="live-empty-state"><strong>No live transcript yet</strong><span>Press Generate live podcast to request an LLM script and start live preview audio.</span></div>}
      </div>
    </section>
  );
}

export function PodcastOutputs({ title, status, summary, playing, onDownload, onNote, onCopyLink }: {
  title: string;
  status: string;
  /** Format, voice count and length, e.g. "Debate - 3 voices - 20 min". */
  summary: string;
  /** The title of the audio in the player, if any. */
  playing: string | null;
  onDownload: (label: string) => void;
  onNote: (message: string) => void;
  onCopyLink: () => void;
}) {
  return (
    <article className="podcast-card podcast-output-panel live-output-panel">
      <h3>Podcast outputs</h3>
      <div className="output-layout">
        <div className="cover-art">AI<br />EVERYDAY<br />LIFE</div>
        <div className="output-copy"><h4>{title || 'Untitled episode'} <span>{status}</span></h4><small>{summary}</small>{playing ? <em>{playing}</em> : null}</div>
        <div className="download-grid"><button type="button" disabled={!playing} onClick={() => onDownload('MP3')}>MP3</button><button type="button" disabled={!playing} onClick={() => onDownload('WAV')}>WAV</button><button type="button" onClick={() => onNote('Transcript export requested.')}>Transcript</button><button type="button" onClick={() => onNote('Show notes export requested.')}>Show Notes</button><button type="button" onClick={onCopyLink}>Copy link</button></div>
      </div>
    </article>
  );
}

/** The run's progress bar under Generate: the whole run (script, preview, final render) as one percentage. */
export function PodcastRunProgress({ progress }: { progress: RunProgress }) {
  const percent = runPercent(progress);
  return (
    <div className="podcast-run-progress">
      <div className="podcast-run-progress-copy"><span>{progress.label}</span><b>{percent}%</b></div>
      <progress aria-label="Podcast progress" max={100} value={percent} />
    </div>
  );
}
