import { useEffect, useState } from 'react';
import type {
  RpgAuthoringDocumentBlock,
  RpgAuthoringPage,
  RpgAuthoringSection,
} from '../../api/rpgWorldAuthoringClient';
import type { RpgWorldSummary } from '../../api/rpgWorldLibraryClient';
import { RpgWorldTopicEditor } from './RpgWorldTopicEditor';
import './RpgWorldAuthoringPage.css';

interface RpgWorldAuthoringPageProps {
  error?: string;
  isLoading: boolean;
  isSaving: boolean;
  onSaveWorld: (changes: Record<string, unknown>) => void;
  page?: RpgAuthoringPage;
  section: RpgAuthoringSection;
  world: RpgWorldSummary;
  worldId: string;
}

function displayValue(value: unknown): string {
  if (value == null) return '';
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') return String(value);
  return JSON.stringify(value, null, 2);
}

function FactBlock({ block }: { block: RpgAuthoringDocumentBlock }) {
  const items = block.items ?? [];
  return (
    <section className="rpg-authoring-document-block">
      {block.title ? <h3>{block.title}</h3> : null}
      <dl className="rpg-authoring-fact-grid">
        {items.map((item, index) => {
          const label = displayValue(item.label ?? item.name ?? item.key ?? `Fact ${index + 1}`);
          const value = displayValue(item.value ?? item.description ?? item.fact ?? item);
          return <div key={`${label}:${index}`}><dt>{label}</dt><dd>{value}</dd></div>;
        })}
      </dl>
    </section>
  );
}

function DocumentBlock({ block }: { block: RpgAuthoringDocumentBlock }) {
  if (block.kind === 'facts') return <FactBlock block={block} />;
  if (block.kind === 'json') {
    return (
      <details className="rpg-authoring-structured-data">
        <summary>{block.title || 'Structured canon'}</summary>
        <pre>{JSON.stringify(block.value, null, 2)}</pre>
      </details>
    );
  }
  return (
    <section className="rpg-authoring-document-block">
      {block.title ? <h3>{block.title}</h3> : null}
      <p style={{ whiteSpace: 'pre-line' }}>{block.body || ''}</p>
    </section>
  );
}

export function RpgWorldAuthoringPage({
  error,
  isLoading,
  isSaving,
  onSaveWorld,
  page,
  section,
  world,
  worldId,
}: RpgWorldAuthoringPageProps) {
  const [isEditingOverview, setIsEditingOverview] = useState(false);
  const [title, setTitle] = useState(world.title);
  const [description, setDescription] = useState(world.description);
  const [genre, setGenre] = useState(world.genre);
  const [tone, setTone] = useState(world.tone);
  const [seed, setSeed] = useState(world.seed);

  useEffect(() => {
    setTitle(world.title);
    setDescription(world.description);
    setGenre(world.genre);
    setTone(world.tone);
    setSeed(world.seed);
  }, [world]);

  if (isLoading) return <section className="rpg-authoring-page"><h2>{section.label}</h2><p>Loading world content…</p></section>;
  if (error) return <section className="rpg-authoring-page"><h2>{section.label}</h2><p className="rpg-world-catalog-error">{error}</p></section>;

  if (section.id === 'overview' && isEditingOverview) {
    return (
      <section className="rpg-authoring-page">
        <p className="eyebrow">Workspace</p>
        <div className="rpg-authoring-page-heading"><h2>Edit World Overview</h2><button className="rpg-secondary-button" type="button" onClick={() => setIsEditingOverview(false)}>Cancel</button></div>
        <form className="rpg-authoring-overview-form" onSubmit={(event) => {
          event.preventDefault();
          onSaveWorld({ title, description, genre, tone, seed });
          setIsEditingOverview(false);
        }}>
          <label><span>Title</span><input required value={title} onChange={(event) => setTitle(event.currentTarget.value)} /></label>
          <label><span>Description</span><textarea rows={5} value={description} onChange={(event) => setDescription(event.currentTarget.value)} /></label>
          <label><span>Genre</span><input value={genre} onChange={(event) => setGenre(event.currentTarget.value)} /></label>
          <label><span>Tone</span><input value={tone} onChange={(event) => setTone(event.currentTarget.value)} /></label>
          <label><span>Seed</span><input type="number" value={seed} onChange={(event) => setSeed(Number(event.currentTarget.value))} /></label>
          <button type="submit" disabled={isSaving}>{isSaving ? 'Saving…' : 'Save World'}</button>
        </form>
      </section>
    );
  }

  if (!page) {
    return <section className="rpg-authoring-page"><h2>{section.label}</h2><div className="rpg-authoring-empty"><h3>Not generated yet</h3><p>This section will populate as world generation completes.</p></div></section>;
  }

  if (page.page_kind === 'collection') {
    return (
      <section className="rpg-authoring-page">
        <div className="rpg-authoring-page-heading"><div><p className="eyebrow">{section.group}</p><h2>{page.title || section.label}</h2></div><span>{page.entities.length} entr{page.entities.length === 1 ? 'y' : 'ies'}</span></div>
        {!page.entities.length ? <div className="rpg-authoring-empty"><h3>No entries yet</h3><p>Generate this section to add structured world entities.</p></div> : null}
        <div className="rpg-authoring-entity-grid">
          {page.entities.map((entity) => (
            <article key={entity.id}>
              <div className="rpg-authoring-entity-placeholder" aria-hidden="true">{entity.title.slice(0, 1).toUpperCase()}</div>
              <div><h3>{entity.title}</h3><p>{entity.summary}</p><small>{entity.kind} · {entity.id}</small></div>
              <details><summary>Structured details</summary><pre>{JSON.stringify(entity.metadata, null, 2)}</pre></details>
            </article>
          ))}
        </div>
        {page.topic ? <RpgWorldTopicEditor topic={page.topic} worldId={worldId} /> : null}
      </section>
    );
  }

  return (
    <section className="rpg-authoring-page">
      <div className="rpg-authoring-page-heading">
        <div><p className="eyebrow">{section.group}</p><h2>{page.title || section.label}</h2></div>
        {section.id === 'overview' ? <button className="rpg-secondary-button" type="button" onClick={() => setIsEditingOverview(true)}>Edit</button> : null}
      </div>
      {page.summary ? <p className="rpg-authoring-page-summary">{page.summary}</p> : null}
      {page.body.length ? page.body.map((block, index) => <DocumentBlock key={`${block.kind}:${index}`} block={block} />) : <div className="rpg-authoring-empty"><h3>Not generated yet</h3><p>This section will populate as world generation completes.</p></div>}
      {page.topic ? <RpgWorldTopicEditor topic={page.topic} worldId={worldId} /> : null}
    </section>
  );
}
