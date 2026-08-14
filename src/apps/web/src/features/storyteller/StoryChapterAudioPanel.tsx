import { useEffect, useMemo, useState } from 'react';
import { readStorySnapshot } from './StoryAudioPanel';
import { buildChapterAudioStates, documentFromCurrentStory, manifestForChapter, upsertStoryAudioManifest, type StoryAudioChapterState } from './storyAudioManifest';

export function StoryChapterAudioPanel() {
  const [snapshot, setSnapshot] = useState(() => readStorySnapshot());
  const document = useMemo(() => documentFromCurrentStory(snapshot.title, snapshot.text), [snapshot.title, snapshot.text]);
  const [chapterStates, setChapterStates] = useState<StoryAudioChapterState[]>(() => buildChapterAudioStates(document));

  useEffect(() => {
    const refresh = () => {
      const nextSnapshot = readStorySnapshot();
      setSnapshot(nextSnapshot);
      const nextDocument = documentFromCurrentStory(nextSnapshot.title, nextSnapshot.text);
      setChapterStates(buildChapterAudioStates(nextDocument));
    };
    refresh();
    const intervalId = window.setInterval(refresh, 1_500);
    window.addEventListener('focus', refresh);
    return () => {
      window.clearInterval(intervalId);
      window.removeEventListener('focus', refresh);
    };
  }, []);

  function markChapterForRegeneration(chapterId: string): void {
    upsertStoryAudioManifest(document.id, manifestForChapter(document, chapterId));
    setChapterStates(buildChapterAudioStates(document));
  }

  return (
    <section className="storyteller-cast-panel" aria-label="Chapter audio status">
      <div className="storyteller-cast-heading">
        <div><p className="eyebrow">Chapter audio</p><h3>Incremental generation status</h3></div>
        <strong>{chapterStates.filter((chapter) => chapter.status === 'ready').length}/{chapterStates.length} ready</strong>
      </div>
      <p>Each chapter tracks its text fingerprint and voice-cast fingerprint. Changed chapters are marked stale so only affected narration needs regeneration.</p>
      <div className="storyteller-voice-cast-table">
        {chapterStates.map((chapter, index) => (
          <article className="storyteller-voice-row" key={chapter.chapterId}>
            <div><strong>{chapter.chapterTitle || `Chapter ${index + 1}`}</strong><span>{chapter.chapterId}</span></div>
            <div><strong>{chapter.status}</strong><span>{chapter.textFingerprint}</span></div>
            <button type="button" onClick={() => markChapterForRegeneration(chapter.chapterId)}>{chapter.status === 'ready' ? 'Mark stale' : 'Queue chapter'}</button>
          </article>
        ))}
      </div>
    </section>
  );
}
