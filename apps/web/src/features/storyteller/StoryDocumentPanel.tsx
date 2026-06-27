import { useEffect, useMemo, useState } from 'react';
import { readStorySnapshot } from './StoryAudioPanel';
import { validateDialogueAttribution } from './storyAttribution';
import { allStoryBlocks, buildStoryDocumentFromText, loadStoryDocument, saveStoryDocument, storyDocumentFingerprint, type StoryDocument } from './storyDocument';

export function StoryDocumentPanel() {
  const [document, setDocument] = useState<StoryDocument>(() => {
    const snapshot = readStorySnapshot();
    return buildStoryDocumentFromText({ title: snapshot.title, text: snapshot.text, existing: loadStoryDocument(`${snapshot.title}:${snapshot.fingerprint}`) });
  });
  const blocks = useMemo(() => allStoryBlocks(document), [document]);
  const attribution = useMemo(() => validateDialogueAttribution(document), [document]);
  const dialogueCount = useMemo(() => blocks.filter((block) => block.kind === 'dialogue').length, [blocks]);

  useEffect(() => {
    const refreshDocument = () => {
      const snapshot = readStorySnapshot();
      const existing = loadStoryDocument(document.id);
      const next = buildStoryDocumentFromText({ title: snapshot.title, text: snapshot.text, existing });
      saveStoryDocument(next);
      setDocument(next);
    };
    refreshDocument();
    const intervalId = window.setInterval(refreshDocument, 1_500);
    window.addEventListener('focus', refreshDocument);
    return () => {
      window.clearInterval(intervalId);
      window.removeEventListener('focus', refreshDocument);
    };
  }, [document.id]);

  return (
    <section className="storyteller-cast-panel" aria-label="Structured story document">
      <div className="storyteller-cast-heading">
        <div><p className="eyebrow">Structured document</p><h3>Generation contract preview</h3></div>
        <strong>{blocks.length} blocks</strong>
      </div>
      <p>Storyteller keeps a structured document with chapters, narration blocks, dialogue blocks, cast, and audio metadata. Dialogue speaker ids are validated against the cast before they are used for audio.</p>
      <div className="storyteller-cast-list">
        <article className="storyteller-cast-card"><div><strong>{document.chapters.length}</strong><span>chapters</span></div><small>{document.title}</small></article>
        <article className="storyteller-cast-card"><div><strong>{dialogueCount}</strong><span>dialogue blocks</span></div><small>{attribution.highConfidence} high-confidence attributions</small></article>
        <article className="storyteller-cast-card"><div><strong>{attribution.narratorFallbacks}</strong><span>narrator fallbacks</span></div><small>{attribution.warnings.length} attribution notes</small></article>
        <article className="storyteller-cast-card"><div><strong>{document.cast.length}</strong><span>cast records</span></div><small>{storyDocumentFingerprint(document)}</small></article>
      </div>
    </section>
  );
}
