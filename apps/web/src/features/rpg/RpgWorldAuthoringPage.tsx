import { useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import type {
  RpgAuthoringDocumentBlock,
  RpgAuthoringPage,
  RpgAuthoringSection,
} from '../../api/rpgWorldAuthoringClient';
import { rpgWorldImageClient } from '../../api/rpgWorldImageClient';
import type { RpgWorldSummary } from '../../api/rpgWorldLibraryClient';
import { RpgWorldEntityCard } from './RpgWorldEntityCard';
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

function humanize(value: string): string {
  return value.replace(/[_-]+/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
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
  const [collectionSearch, setCollectionSearch] = useState('');
  const [collectionKind, setCollectionKind] = useState('all');
  const [collectionSort, setCollectionSort] = useState('name');
  const imagesQuery = useQuery({
    queryKey: ['feature', 'rpg', 'world-image-targets', worldId],
    queryFn: () => rpgWorldImageClient.list(worldId),
    enabled: page?.page_kind === 'collection' && section.id !== 'images',
    staleTime: 10_000,
  });
  const approvedAssets = useMemo(() => new Map(
    (imagesQuery.data?.targets ?? [])
      .filter((target) => target.review_state === 'approved' && target.active_asset_id)
      .map((target) => [target.entity_id, String(target.active_asset_id)]),
  ), [imagesQuery.data?.targets]);
  const collectionEntities = page?.page_kind === 'collection' ? page.entities : [];
  const collectionKinds = useMemo(
    () => Array.from(new Set(collectionEntities.map((entity) => entity.kind))).sort(),
    [collectionEntities],
  );
  const visibleEntities = useMemo(() => {
    const query = collectionSearch.trim().toLowerCase();
    return [...collectionEntities]
      .filter((entity) => collectionKind === 'all' || entity.kind === collectionKind)
      .filter((entity) => !query || [entity.title, entity.summary, entity.kind, entity.id]
        .some((value) => value.toLowerCase().includes(query)))
      .sort((left, right) => {
        if (collectionSort === 'type') {
          const kindOrder = left.kind.localeCompare(right.kind);
          if (kindOrder) return kindOrder;
        }
        return left.title.localeCompare(right.title);
      });
  }, [collectionEntities, collectionKind, collectionSearch, collectionSort]);

  useEffect(() => {
    setTitle(world.title);
    setDescription(world.description);
    setGenre(world.genre);
    setTone(world.tone);
    setSeed(world.seed);
  }, [world]);

  useEffect(() => {
    setCollectionSearch('');
    setCollectionKind('all');
    setCollectionSort('name');
  }, [section.id]);

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
        <div className="rpg-authoring-page-heading"><div><p className="eyebrow">{section.group}</p><h2>{page.title || section.label}</h2></div><span>{visibleEntities.length === page.entities.length ? page.entities.length : `${visibleEntities.length} of ${page.entities.length}`} entr{page.entities.length === 1 ? 'y' : 'ies'}</span></div>
        {page.entities.length ? (
          <div className="rpg-authoring-collection-toolbar">
            <input aria-label={`Search ${page.title || section.label}`} placeholder={`Search ${page.title || section.label.toLowerCase()}…`} value={collectionSearch} onChange={(event) => setCollectionSearch(event.currentTarget.value)} />
            <select aria-label={`Filter ${page.title || section.label} by type`} value={collectionKind} onChange={(event) => setCollectionKind(event.currentTarget.value)}>
              <option value="all">All types</option>
              {collectionKinds.map((kind) => <option key={kind} value={kind}>{humanize(kind)}</option>)}
            </select>
            <select aria-label={`Sort ${page.title || section.label}`} value={collectionSort} onChange={(event) => setCollectionSort(event.currentTarget.value)}>
              <option value="name">Sort by name</option>
              <option value="type">Sort by type</option>
            </select>
          </div>
        ) : null}
        {!page.entities.length ? <div className="rpg-authoring-empty"><h3>No entries yet</h3><p>Generate this section to add structured world entities.</p></div> : null}
        {page.entities.length && !visibleEntities.length ? <div className="rpg-authoring-empty"><h3>No matching entries</h3><p>Clear the search or choose a different type.</p></div> : null}
        <div className="rpg-authoring-entity-grid">
          {visibleEntities.map((entity) => (
            <RpgWorldEntityCard
              entity={entity}
              imageAssetId={approvedAssets.get(entity.id)}
              key={entity.id}
              topic={page.topic}
              worldId={worldId}
            />
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
