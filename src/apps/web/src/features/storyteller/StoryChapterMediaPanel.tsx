import { useEffect, useMemo, useState } from 'react';
import { readStorySnapshot } from './StoryAudioPanel';
import { buildChapterAudioStates, documentFromCurrentStory } from './storyAudioManifest';

export function StoryChapterMediaPanel() {
  const [snapshot, setSnapshot] = useState(() => readStorySnapshot());
  const storyDoc = useMemo(() => documentFromCurrentStory(snapshot.title, snapshot.text), [snapshot.title, snapshot.text]);
  const chapterStates = useMemo(() => buildChapterAudioStates(storyDoc), [storyDoc]);
  const readyCount = chapterStates.filter((chapter) => chapter.status === 'ready').length;

  useEffect(() => {
    const refresh = () => setSnapshot(readStorySnapshot());
    const intervalId = window.setInterval(refresh, 1_500);
    window.addEventListener('focus', refresh);
    return () => {
      window.clearInterval(intervalId);
      window.removeEventListener('focus', refresh);
    };
  }, []);

  return (
    <section className="storyteller-cast-panel" aria-label="Story chapter media">
      <div className="storyteller-cast-heading">
        <div><p className="eyebrow">Chapter media</p><h3>Player queue</h3></div>
        <strong>{readyCount}/{chapterStates.length} ready</strong>
      </div>
      <p>Generated chapter outputs are listed here so the story can be played in sequence and packaged after chapter media is ready.</p>
      <div className="storyteller-voice-cast-table">
        {chapterStates.map((chapter, index) => (
          <article className="storyteller-voice-row" key={chapter.chapterId}>
            <div><strong>{chapter.chapterTitle || `Chapter ${index + 1}`}</strong><span>{chapter.chapterId}</span></div>
            <div><strong>{chapter.status}</strong><span>{chapter.manifest?.downloadFilename ?? 'No file yet'}</span></div>
            <button type="button" disabled={chapter.status !== 'ready'}>Play</button>
          </article>
        ))}
      </div>
    </section>
  );
}
