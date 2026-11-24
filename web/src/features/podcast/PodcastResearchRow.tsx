import { useState } from 'react';
import { researchPodcastTopic } from './podcastResearch';

/** "Research the topic": one web search on the title and brief; what it finds goes to the producer's notes. */
export function PodcastResearchRow({ title, brief, onNotes }: { title: string; brief: string; onNotes: (notes: string) => void }) {
  const [researching, setResearching] = useState(false);
  const [note, setNote] = useState('');

  async function research() {
    setResearching(true);
    setNote('Searching the web for this topic...');
    try {
      const result = await researchPodcastTopic(title, brief);
      if (result.status === 'ok') onNotes(result.notes);
      setNote(result.message);
    } catch (error) {
      setNote(error instanceof Error ? error.message : 'The web search failed.');
    } finally {
      setResearching(false);
    }
  }

  return (
    <div className="podcast-research-row">
      <button className="ghost-button compact" type="button" disabled={researching || !(title.trim() || brief.trim())} onClick={() => void research()}>{researching ? 'Researching...' : 'Research the topic'}</button>
      <small>{note || 'One web search on the title and brief; the notes it finds are added above for you to check.'}</small>
    </div>
  );
}
