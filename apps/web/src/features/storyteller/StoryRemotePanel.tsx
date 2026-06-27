import { useMemo, useState } from 'react';
import { readStorySnapshot } from './StoryAudioPanel';
import { buildStoryDocumentFromText } from './storyDocument';
import { tryStoreStoryDocument, validateStoryDocumentForRemote } from './storyRemoteStore';

export function StoryRemotePanel() {
  const snapshot = readStorySnapshot();
  const storyDoc = useMemo(() => buildStoryDocumentFromText({ title: snapshot.title, text: snapshot.text }), [snapshot.title, snapshot.text]);
  const issues = useMemo(() => validateStoryDocumentForRemote(storyDoc), [storyDoc]);
  const [message, setMessage] = useState('Local story metadata is ready.');

  async function testStore(): Promise<void> {
    const result = await tryStoreStoryDocument(storyDoc);
    setMessage(result.message);
  }

  return (
    <section className="storyteller-cast-panel" aria-label="Story remote status">
      <div className="storyteller-cast-heading">
        <div><p className="eyebrow">Remote status</p><h3>Metadata checks</h3></div>
        <strong>{issues.length ? `${issues.length} issues` : 'valid'}</strong>
      </div>
      <p>{message}</p>
      <div className="storyteller-audio-actions"><button type="button" onClick={() => void testStore()}>Test remote save</button></div>
      <div className="storyteller-cast-list">
        <article className="storyteller-cast-card"><div><strong>{storyDoc.chapters.length}</strong><span>chapters</span></div><small>{storyDoc.id}</small></article>
        <article className="storyteller-cast-card"><div><strong>{storyDoc.cast.length}</strong><span>cast members</span></div><small>{issues[0] ?? 'Ready for validation'}</small></article>
      </div>
    </section>
  );
}
