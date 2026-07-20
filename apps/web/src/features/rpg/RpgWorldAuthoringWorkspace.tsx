import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { omnixApiClient } from '../../api/client';
import {
  rpgWorldLibraryClient,
  type RpgScenarioRevision,
  type RpgWorldRelease,
  type RpgWorldSummary,
} from '../../api/rpgWorldLibraryClient';
import { RpgWorldCard } from './RpgWorldCard';
import { RpgWorldEditorShell } from './RpgWorldEditorShell';
import './RpgWorldAuthoringWorkspace.css';

interface RpgWorldAuthoringWorkspaceProps {
  onBack: () => void;
  onSessionLaunched: (sessionId: string) => void;
}

type WorldWorkspaceView =
  | { kind: 'library' }
  | { kind: 'editor'; worldId: string }
  | { kind: 'campaignSetup'; worldId: string };

function slug(value: string): string {
  const normalized = value.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
  return normalized || 'new-world';
}

function timestamp(value: string): number {
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function matchingRelease(releases: RpgWorldRelease[], revision: RpgScenarioRevision | undefined) {
  if (!revision) return undefined;
  const compatibleRelease = Number(record(revision.document).compatible_release || 0);
  return releases.find((release) => (
    release.world_revision === revision.world_revision
    && (!compatibleRelease || release.release === compatibleRelease)
  ));
}

function worldState(world: RpgWorldSummary): string {
  const generation = world.generation;
  if (world.status === 'archived') return 'Archived';
  if (generation?.status === 'running' || generation?.status === 'planned') return 'Generating';
  if (generation?.status === 'failed') return 'Generation failed';
  return world.status === 'published' ? 'Published' : 'Draft';
}

export function RpgWorldAuthoringWorkspace({ onBack, onSessionLaunched }: RpgWorldAuthoringWorkspaceProps) {
  const queryClient = useQueryClient();
  const [view, setView] = useState<WorldWorkspaceView>({ kind: 'library' });
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [showCreate, setShowCreate] = useState(false);
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [genre, setGenre] = useState('classic_fantasy');
  const [tone, setTone] = useState('heroic adventure');
  const [feedback, setFeedback] = useState('');

  const libraryQuery = useQuery({
    queryKey: ['feature', 'rpg', 'world-authoring-workspace'],
    queryFn: () => rpgWorldLibraryClient.list(),
    refetchInterval: 5000,
  });
  const selectedWorldId = view.kind === 'editor' || view.kind === 'campaignSetup' ? view.worldId : '';
  const detailQuery = useQuery({
    queryKey: ['feature', 'rpg', 'world-authoring-workspace', selectedWorldId],
    queryFn: () => rpgWorldLibraryClient.detail(selectedWorldId),
    enabled: Boolean(selectedWorldId),
    refetchInterval: 5000,
  });

  const refresh = async () => queryClient.invalidateQueries({ queryKey: ['feature', 'rpg'] });
  const createWorld = useMutation({
    mutationFn: () => rpgWorldLibraryClient.createWorld({
      world_id: `world:${slug(title)}:${Date.now().toString(36)}`,
      title: title.trim(),
      description: description.trim(),
      source_mode: 'hybrid',
      genre,
      tone,
      seed: 0,
      metadata: { campaign_template: genre },
    }),
    onSuccess: async (result) => {
      setShowCreate(false);
      setTitle('');
      setDescription('');
      setFeedback(`Created ${result.world.title}.`);
      await refresh();
      setView({ kind: 'editor', worldId: result.world.id });
    },
  });
  const lifecycle = useMutation({
    mutationFn: (world: RpgWorldSummary) => world.status === 'archived'
      ? rpgWorldLibraryClient.restoreWorld(world.id)
      : rpgWorldLibraryClient.archiveWorld(world.id),
    onSuccess: async () => refresh(),
  });
  const continueCampaign = useMutation({
    mutationFn: (campaignId: string) => omnixApiClient.continueRpgSession(campaignId),
    onSuccess: (result) => {
      if (!result.ok || !result.session_id) throw new Error(result.error ?? 'Campaign could not be continued.');
      onSessionLaunched(result.session_id);
    },
  });
  const launchScenario = useMutation({
    mutationFn: async (scenarioId: string) => {
      const detail = detailQuery.data;
      if (!detail) throw new Error('World detail is not available.');
      const revision = [...(detail.scenario_revisions[scenarioId] ?? [])]
        .sort((left, right) => right.revision - left.revision)[0];
      const release = matchingRelease(detail.releases, revision);
      if (!revision || !release) throw new Error('This opening does not have a compatible published release.');
      return rpgWorldLibraryClient.launchScenario(scenarioId, revision.revision, {
        world_id: detail.world.id,
        world_revision: revision.world_revision,
        world_release: release.release,
        player: { name: 'Alyndra', pronouns: 'they/them', background: 'World Traveler', build: 'balanced_adventurer' },
        gameplay: {},
        features: {},
      });
    },
    onSuccess: (result) => {
      if (!result.ok || !result.session_id) throw new Error(result.error ?? 'Campaign launch failed.');
      onSessionLaunched(result.session_id);
    },
  });

  const visibleWorlds = useMemo(() => {
    const query = search.trim().toLowerCase();
    return [...(libraryQuery.data?.worlds ?? [])]
      .filter((world) => statusFilter === 'all' || worldState(world).toLowerCase().replace(/\s+/g, '-') === statusFilter)
      .filter((world) => !query || [world.title, world.description, world.genre, world.tone]
        .some((value) => value.toLowerCase().includes(query)))
      .sort((left, right) => timestamp(right.updated_at) - timestamp(left.updated_at));
  }, [libraryQuery.data?.worlds, search, statusFilter]);

  if (view.kind === 'library') {
    return (
      <section className="rpg-authoring-library" aria-label="World library">
        <header className="rpg-authoring-heading">
          <div><p className="eyebrow">RPG authoring</p><h2>Worlds</h2><p>Create reusable worlds, then edit or play them.</p></div>
          <div><button className="rpg-secondary-button" type="button" onClick={onBack}>Back to Play</button><button type="button" onClick={() => setShowCreate(true)}>Create New World</button></div>
        </header>
        <div className="rpg-authoring-toolbar">
          <input aria-label="Search world library" placeholder="Search by title, genre, or tone…" value={search} onChange={(event) => setSearch(event.currentTarget.value)} />
          <select aria-label="Filter worlds" value={statusFilter} onChange={(event) => setStatusFilter(event.currentTarget.value)}>
            <option value="all">All worlds</option><option value="draft">Draft</option><option value="published">Published</option><option value="archived">Archived</option><option value="generating">Generating</option><option value="generation-failed">Generation failed</option>
          </select>
        </div>
        {feedback ? <p className="rpg-authoring-feedback">{feedback}</p> : null}
        {libraryQuery.isPending ? <p>Loading worlds…</p> : null}
        {libraryQuery.isError ? <p className="rpg-world-catalog-error">Unable to load worlds.</p> : null}
        <div className="rpg-world-card-grid">
          {visibleWorlds.map((world) => {
            const scenarioCount = (libraryQuery.data?.scenarios ?? []).filter((scenario) => scenario.world_id === world.id && scenario.status === 'published').length;
            const campaignCount = (libraryQuery.data?.campaigns ?? []).filter((campaign) => campaign.world_id === world.id && campaign.status !== 'archived').length;
            return (
              <RpgWorldCard
                key={world.id}
                world={world}
                facts={<><span>{worldState(world)}</span><span>{scenarioCount} opening{scenarioCount === 1 ? '' : 's'}</span><span>{campaignCount} campaign{campaignCount === 1 ? '' : 's'}</span></>}
                actions={<><button className="rpg-secondary-button" type="button" onClick={() => setView({ kind: 'editor', worldId: world.id })}>Edit</button><button type="button" onClick={() => setView({ kind: 'campaignSetup', worldId: world.id })}>Play</button></>}
                footer={<details className="rpg-world-card-more"><summary>More</summary><button className="rpg-secondary-button" type="button" onClick={() => lifecycle.mutate(world)}>{world.status === 'archived' ? 'Restore' : 'Archive'}</button></details>}
              />
            );
          })}
        </div>
        {!libraryQuery.isPending && !visibleWorlds.length ? <p>No worlds match this view.</p> : null}
        {showCreate ? (
          <div className="rpg-authoring-modal" role="dialog" aria-modal="true" aria-label="Create new world">
            <form onSubmit={(event) => { event.preventDefault(); createWorld.mutate(); }}>
              <h3>Create New World</h3>
              <label><span>Title</span><input required value={title} onChange={(event) => setTitle(event.currentTarget.value)} /></label>
              <label><span>Description</span><textarea value={description} onChange={(event) => setDescription(event.currentTarget.value)} /></label>
              <label><span>Genre</span><input value={genre} onChange={(event) => setGenre(event.currentTarget.value)} /></label>
              <label><span>Tone</span><input value={tone} onChange={(event) => setTone(event.currentTarget.value)} /></label>
              <div><button className="rpg-secondary-button" type="button" onClick={() => setShowCreate(false)}>Cancel</button><button type="submit" disabled={createWorld.isPending}>Create World</button></div>
            </form>
          </div>
        ) : null}
      </section>
    );
  }

  const world = libraryQuery.data?.worlds.find((candidate) => candidate.id === view.worldId) ?? detailQuery.data?.world;
  if (view.kind === 'campaignSetup') {
    const campaigns = (libraryQuery.data?.campaigns ?? []).filter((campaign) => campaign.world_id === view.worldId && campaign.status !== 'archived');
    const scenarios = (detailQuery.data?.scenarios ?? []).filter((scenario) => scenario.status === 'published');
    return (
      <section className="rpg-authoring-campaign-setup" aria-label="World campaign setup">
        <header className="rpg-authoring-heading"><div><p className="eyebrow">Campaign setup</p><h2>{world?.title ?? 'World'}</h2><p>Continue a campaign or start from a published opening.</p></div><button className="rpg-secondary-button" type="button" onClick={() => setView({ kind: 'library' })}>Back to Worlds</button></header>
        <div className="rpg-authoring-two-column">
          <section><h3>Continue Campaign</h3>{campaigns.map((campaign) => <article key={campaign.campaign_id}><div><strong>{campaign.title}</strong><p>{campaign.status}</p></div><button type="button" disabled={continueCampaign.isPending} onClick={() => continueCampaign.mutate(campaign.campaign_id)}>Continue</button></article>)}{!campaigns.length ? <p>No campaigns have started in this world.</p> : null}</section>
          <section><h3>Start New Campaign</h3>{scenarios.map((scenario) => <article key={scenario.id}><div><strong>{scenario.title}</strong><p>{scenario.description || 'Published opening scenario'}</p></div><button type="button" disabled={launchScenario.isPending} onClick={() => launchScenario.mutate(scenario.id)}>Play</button></article>)}{!scenarios.length ? <><p>World setup is incomplete. Publish an opening scenario before play.</p><button type="button" onClick={() => setView({ kind: 'editor', worldId: view.worldId })}>Review World Setup</button></> : null}</section>
        </div>
      </section>
    );
  }

  if (!world) return <p>Loading world editor…</p>;
  return (
    <RpgWorldEditorShell
      onBack={() => setView({ kind: 'library' })}
      onPlay={() => setView({ kind: 'campaignSetup', worldId: view.worldId })}
      onSessionLaunched={onSessionLaunched}
      world={world}
      worldId={view.worldId}
    />
  );
}
