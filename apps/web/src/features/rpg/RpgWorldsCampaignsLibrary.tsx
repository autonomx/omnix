import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  rpgWorldLibraryClient,
  type RpgScenarioRevision,
  type RpgWorldDetailResponse,
  type RpgWorldGenerationRun,
  type RpgWorldRelease,
} from '../../api/rpgWorldLibraryClient';
import './RpgWorldsCampaignsLibrary.css';

interface RpgWorldsCampaignsLibraryProps {
  onBack: () => void;
  onSessionLaunched: (sessionId: string) => void;
}

type LibraryTab = 'worlds' | 'campaigns';

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function array(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function text(value: unknown, fallback = ''): string {
  return typeof value === 'string' && value.trim() ? value.trim() : fallback;
}

function number(value: unknown, fallback = 0): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback;
}

function pretty(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

function certification(release: RpgWorldRelease | undefined): Record<string, unknown> {
  return record(record(release?.document).certification);
}

function matchingRelease(
  detail: RpgWorldDetailResponse,
  scenario: RpgScenarioRevision,
): RpgWorldRelease | undefined {
  const compatibleRelease = number(record(scenario.document).compatible_release);
  return detail.releases.find((release) => (
    release.world_revision === scenario.world_revision
    && (!compatibleRelease || release.release === compatibleRelease)
  ));
}

function generationLabel(run: RpgWorldGenerationRun | null | undefined): string {
  if (!run) return 'Not generated';
  const progress = record(run.progress);
  const percent = number(progress.percent);
  return `${run.status}${percent ? ` • ${percent}%` : ''}`;
}

export function RpgWorldsCampaignsLibrary({
  onBack,
  onSessionLaunched,
}: RpgWorldsCampaignsLibraryProps) {
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<LibraryTab>('worlds');
  const [selectedWorldId, setSelectedWorldId] = useState('');
  const [worldId, setWorldId] = useState('world:new');
  const [worldTitle, setWorldTitle] = useState('New World');
  const [worldDescription, setWorldDescription] = useState('');
  const [worldGenre, setWorldGenre] = useState('classic_fantasy');
  const [worldTone, setWorldTone] = useState('heroic adventure');
  const [generationDepth, setGenerationDepth] = useState('standard');
  const [startingLocation, setStartingLocation] = useState('rusty_flagon_tavern');
  const [topicId, setTopicId] = useState('realm');
  const [topicJson, setTopicJson] = useState('{\n  "topic_id": "realm",\n  "documents": [],\n  "entities": [],\n  "facts": []\n}');
  const [scenarioId, setScenarioId] = useState('scenario:opening');
  const [scenarioTitle, setScenarioTitle] = useState('Opening Scenario');
  const [scenarioLocation, setScenarioLocation] = useState('rusty_flagon_tavern');
  const [playerName, setPlayerName] = useState('Alyndra');
  const [feedback, setFeedback] = useState<string>();
  const [error, setError] = useState<string>();

  const libraryQuery = useQuery({
    queryKey: ['feature', 'rpg', 'world-library'],
    queryFn: () => rpgWorldLibraryClient.list(),
    refetchInterval: 5000,
  });
  const detailQuery = useQuery({
    queryKey: ['feature', 'rpg', 'world-library', selectedWorldId],
    queryFn: () => rpgWorldLibraryClient.detail(selectedWorldId),
    enabled: Boolean(selectedWorldId),
    refetchInterval: 5000,
  });

  useEffect(() => {
    if (!selectedWorldId && libraryQuery.data?.worlds[0]?.id) {
      setSelectedWorldId(libraryQuery.data.worlds[0].id);
    }
  }, [libraryQuery.data, selectedWorldId]);

  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['feature', 'rpg', 'world-library'] }),
      queryClient.invalidateQueries({ queryKey: ['feature', 'rpg', 'replay-inventory'] }),
      queryClient.invalidateQueries({ queryKey: ['platform', 'jobs'] }),
    ]);
  };

  const createWorldMutation = useMutation({
    mutationFn: () => rpgWorldLibraryClient.createWorld({
      world_id: worldId.trim(),
      title: worldTitle.trim(),
      description: worldDescription.trim(),
      source_mode: 'hybrid',
      genre: worldGenre,
      tone: worldTone,
      seed: 0,
      metadata: { campaign_template: worldGenre },
    }),
    onSuccess: async (result) => {
      setSelectedWorldId(result.world.id);
      setFeedback(`World created: ${result.world.title}`);
      setError(undefined);
      await refresh();
    },
    onError: (cause) => setError(cause instanceof Error ? cause.message : 'World creation failed.'),
  });

  const saveTopicMutation = useMutation({
    mutationFn: () => {
      const content = JSON.parse(topicJson) as Record<string, unknown>;
      return rpgWorldLibraryClient.saveTopic(selectedWorldId, {
        topic_id: topicId.trim(),
        content,
        directives: {},
        status: 'ready',
      });
    },
    onSuccess: async (result) => {
      setFeedback(`Topic saved: ${result.topic.topic_id}`);
      setError(undefined);
      await refresh();
    },
    onError: (cause) => setError(cause instanceof Error ? cause.message : 'Topic save failed.'),
  });

  const generationMutation = useMutation({
    mutationFn: () => rpgWorldLibraryClient.startGeneration(selectedWorldId, {
      depth: generationDepth,
      starting_location: startingLocation,
      background_expansion: true,
      topic_directives: {},
      entity_manifest: {},
    }),
    onSuccess: async (result) => {
      setFeedback(`World generation started: ${result.run.run_id}`);
      setError(undefined);
      await refresh();
    },
    onError: (cause) => setError(cause instanceof Error ? cause.message : 'World generation failed to start.'),
  });

  const publishGenerationMutation = useMutation({
    mutationFn: (runId: string) => rpgWorldLibraryClient.publishGeneration(runId),
    onSuccess: async (result) => {
      setFeedback(`Published world release ${text(record(result.publication).world_release, '1')}.`);
      setError(undefined);
      await refresh();
    },
    onError: (cause) => setError(cause instanceof Error ? cause.message : 'World publication failed.'),
  });

  const createScenarioMutation = useMutation({
    mutationFn: () => rpgWorldLibraryClient.createScenario({
      scenario_id: scenarioId.trim(),
      world_id: selectedWorldId,
      title: scenarioTitle.trim(),
      description: `Opening at ${scenarioLocation}`,
      metadata: { starting_location: scenarioLocation },
    }),
    onSuccess: async (result) => {
      setFeedback(`Scenario created: ${result.scenario.title}`);
      setError(undefined);
      await refresh();
    },
    onError: (cause) => setError(cause instanceof Error ? cause.message : 'Scenario creation failed.'),
  });

  const publishScenarioMutation = useMutation({
    mutationFn: (values: {
      scenarioId: string;
      worldRevision: number;
      worldRevisionHash: string;
      compatibleRelease: number;
    }) => rpgWorldLibraryClient.publishScenario(values.scenarioId, {
      revision: 1,
      world_id: selectedWorldId,
      world_revision: values.worldRevision,
      world_revision_hash: values.worldRevisionHash,
      compatible_release: values.compatibleRelease,
      starting_epoch: 'Day 1',
      starting_location_id: scenarioLocation,
      activated_conflict_ids: [],
      initial_npc_ids: [],
      protagonist_options: [],
      starting_resources: {},
      opening_seed_ids: [],
      map_initialization: [],
      content_hash: '',
    }),
    onSuccess: async (result) => {
      setFeedback(`Scenario revision published: ${result.scenario_revision.revision}`);
      setError(undefined);
      await refresh();
    },
    onError: (cause) => setError(cause instanceof Error ? cause.message : 'Scenario publication failed.'),
  });

  const launchMutation = useMutation({
    mutationFn: (values: {
      scenarioId: string;
      scenarioRevision: number;
      worldRevision: number;
      worldRelease: number;
    }) => rpgWorldLibraryClient.launchScenario(values.scenarioId, values.scenarioRevision, {
      world_id: selectedWorldId,
      world_revision: values.worldRevision,
      world_release: values.worldRelease,
      player: {
        name: playerName.trim() || 'Alyndra',
        pronouns: 'they/them',
        background: 'World Traveler',
        build: 'balanced_adventurer',
      },
      gameplay: {},
      features: {},
    }),
    onSuccess: async (result) => {
      if (!result.ok || !result.session_id) {
        throw new Error(result.error ?? 'Published scenario did not return a session id.');
      }
      setFeedback(`Campaign launched: ${result.session_id}`);
      setError(undefined);
      onSessionLaunched(result.session_id);
      await refresh();
    },
    onError: (cause) => setError(cause instanceof Error ? cause.message : 'Scenario launch failed.'),
  });

  const detail = detailQuery.data;
  const latestRun = detail?.generation_runs[0];
  const latestRevision = detail?.revisions[0];
  const latestRelease = detail?.releases[0];
  const latestCertification = certification(latestRelease);
  const validationFindings = array(latestCertification.missing_requirements).map(String);
  const blueprintRequirements = array(record(latestRevision?.document).blueprint_requirements);
  const launchReady = Boolean(latestCertification.launch_ready);
  const selectedWorld = libraryQuery.data?.worlds.find((world) => world.id === selectedWorldId);
  const worldScenarios = detail?.scenarios ?? [];
  const campaignCountByWorld = useMemo(() => {
    const counts = new Map<string, number>();
    for (const campaign of libraryQuery.data?.campaigns ?? []) {
      counts.set(campaign.world_id, (counts.get(campaign.world_id) ?? 0) + 1);
    }
    return counts;
  }, [libraryQuery.data?.campaigns]);

  return (
    <section className="rpg-world-library" aria-label="Worlds and Campaigns library">
      <header className="rpg-world-library-header">
        <div>
          <p className="eyebrow">RPG authoring</p>
          <h2>Worlds &amp; Campaigns</h2>
          <p>Create reusable worlds, publish immutable releases, author scenarios, and launch campaigns without rebuilding canon.</p>
        </div>
        <button type="button" className="rpg-secondary-button" onClick={onBack}>Back to Play</button>
      </header>

      <nav className="rpg-world-library-tabs" aria-label="Library views">
        <button type="button" aria-pressed={tab === 'worlds'} onClick={() => setTab('worlds')}>Worlds</button>
        <button type="button" aria-pressed={tab === 'campaigns'} onClick={() => setTab('campaigns')}>Campaigns</button>
      </nav>

      {feedback ? <p className="rpg-world-library-feedback" aria-live="polite">{feedback}</p> : null}
      {error ? <p className="rpg-world-library-error" aria-live="assertive">{error}</p> : null}
      {libraryQuery.isError ? <p className="rpg-world-library-error">Unable to load the world library.</p> : null}

      {tab === 'campaigns' ? (
        <div className="rpg-world-library-card-grid" aria-label="Campaign cards">
          {(libraryQuery.data?.campaigns ?? []).map((campaign) => (
            <article className="rpg-world-library-card" key={campaign.campaign_id}>
              <p className="eyebrow">{campaign.status}</p>
              <h3>{campaign.title}</h3>
              <dl>
                <div><dt>Campaign</dt><dd>{campaign.campaign_id}</dd></div>
                <div><dt>World pin</dt><dd>r{campaign.world_revision} / release {campaign.world_release}</dd></div>
                <div><dt>Scenario pin</dt><dd>{campaign.scenario_id} r{campaign.scenario_revision}</dd></div>
              </dl>
            </article>
          ))}
          {!libraryQuery.isPending && !(libraryQuery.data?.campaigns.length) ? (
            <p className="rpg-world-library-empty">No campaigns have been launched from published scenarios.</p>
          ) : null}
        </div>
      ) : (
        <div className="rpg-world-library-layout">
          <aside className="rpg-world-library-sidebar">
            <section className="rpg-world-library-panel">
              <h3>World projects</h3>
              <div className="rpg-world-library-world-list">
                {(libraryQuery.data?.worlds ?? []).map((world) => (
                  <button
                    type="button"
                    className={world.id === selectedWorldId ? 'is-selected' : ''}
                    key={world.id}
                    onClick={() => setSelectedWorldId(world.id)}
                  >
                    <strong>{world.title}</strong>
                    <span>{world.genre} • {world.status}</span>
                    <small>{world.scenario_count ?? 0} scenarios • {campaignCountByWorld.get(world.id) ?? 0} campaigns</small>
                    <small>{generationLabel(world.generation)}</small>
                  </button>
                ))}
              </div>
            </section>

            <form className="rpg-world-library-panel rpg-world-library-form" onSubmit={(event) => { event.preventDefault(); createWorldMutation.mutate(); }}>
              <h3>Create world</h3>
              <label><span>World id</span><input value={worldId} onChange={(event) => setWorldId(event.currentTarget.value)} required /></label>
              <label><span>Title</span><input value={worldTitle} onChange={(event) => setWorldTitle(event.currentTarget.value)} required /></label>
              <label><span>Description</span><textarea value={worldDescription} onChange={(event) => setWorldDescription(event.currentTarget.value)} /></label>
              <label><span>Genre</span><input value={worldGenre} onChange={(event) => setWorldGenre(event.currentTarget.value)} /></label>
              <label><span>Tone</span><input value={worldTone} onChange={(event) => setWorldTone(event.currentTarget.value)} /></label>
              <button type="submit" disabled={createWorldMutation.isPending}>Create reusable world</button>
            </form>
          </aside>

          <main className="rpg-world-library-main">
            {!selectedWorldId ? <p className="rpg-world-library-empty">Create or select a world project.</p> : null}
            {detailQuery.isPending && selectedWorldId ? <p>Loading world detail…</p> : null}
            {detailQuery.isError ? <p className="rpg-world-library-error">Unable to load this world.</p> : null}

            {detail ? (
              <>
                <section className="rpg-world-library-panel rpg-world-library-overview">
                  <div>
                    <p className="eyebrow">{detail.world.status} • {detail.world.source_mode}</p>
                    <h3>{detail.world.title}</h3>
                    <p>{detail.world.description || 'No description yet.'}</p>
                  </div>
                  <dl>
                    <div><dt>Draft</dt><dd>{detail.world.draft_revision}</dd></div>
                    <div><dt>Topics</dt><dd>{detail.topics.length}</dd></div>
                    <div><dt>Revisions</dt><dd>{detail.revisions.length}</dd></div>
                    <div><dt>Releases</dt><dd>{detail.releases.length}</dd></div>
                  </dl>
                </section>

                <div className="rpg-world-library-two-column">
                  <section className="rpg-world-library-panel">
                    <div className="rpg-world-library-section-heading">
                      <div><p className="eyebrow">Durable DAG</p><h3>World generation</h3></div>
                      <span>{generationLabel(latestRun)}</span>
                    </div>
                    <div className="rpg-world-library-inline-form">
                      <label><span>Depth</span><select value={generationDepth} onChange={(event) => setGenerationDepth(event.currentTarget.value)}><option value="quick">Quick</option><option value="standard">Standard</option><option value="epic">Epic</option></select></label>
                      <label><span>Starting location</span><input value={startingLocation} onChange={(event) => setStartingLocation(event.currentTarget.value)} /></label>
                    </div>
                    <div className="rpg-world-library-actions">
                      <button type="button" disabled={generationMutation.isPending} onClick={() => generationMutation.mutate()}>Generate / resume</button>
                      <button type="button" disabled={!latestRun || latestRun.status !== 'review' || publishGenerationMutation.isPending} onClick={() => latestRun && publishGenerationMutation.mutate(latestRun.run_id)}>Publish revision &amp; release</button>
                    </div>
                    {latestRun ? <pre>{pretty(latestRun.progress)}</pre> : <p>No generation run yet.</p>}
                  </section>

                  <section className="rpg-world-library-panel">
                    <p className="eyebrow">Certification</p>
                    <h3>{launchReady ? 'Launch ready' : 'Validation findings'}</h3>
                    {validationFindings.length ? (
                      <ul>{validationFindings.map((finding) => <li key={finding}>{finding}</li>)}</ul>
                    ) : (
                      <p>{latestRelease ? 'No blocking findings in the latest release.' : 'Publish a release to calculate launch readiness.'}</p>
                    )}
                    <p>Simulation readiness and presentation readiness remain independent.</p>
                  </section>
                </div>

                <div className="rpg-world-library-two-column">
                  <form className="rpg-world-library-panel rpg-world-library-form" onSubmit={(event) => { event.preventDefault(); saveTopicMutation.mutate(); }}>
                    <p className="eyebrow">Manual or hybrid authoring</p>
                    <h3>World topic</h3>
                    <label><span>Topic id</span><input value={topicId} onChange={(event) => setTopicId(event.currentTarget.value)} /></label>
                    <label><span>Structured topic JSON</span><textarea rows={12} value={topicJson} onChange={(event) => setTopicJson(event.currentTarget.value)} /></label>
                    <button type="submit" disabled={saveTopicMutation.isPending}>Save topic draft</button>
                  </form>

                  <section className="rpg-world-library-panel">
                    <p className="eyebrow">Topic status</p>
                    <h3>Generated and authored topics</h3>
                    <div className="rpg-world-library-topic-list">
                      {detail.topics.map((topic) => (
                        <article key={topic.topic_id}>
                          <strong>{topic.topic_id}</strong>
                          <span>{topic.status} • {topic.source}</span>
                          <small>{topic.content_hash || 'not hashed'}</small>
                        </article>
                      ))}
                    </div>
                  </section>
                </div>

                <div className="rpg-world-library-two-column">
                  <section className="rpg-world-library-panel">
                    <p className="eyebrow">Spatial foundation</p>
                    <h3>Map-blueprint requirements</h3>
                    {blueprintRequirements.length ? <pre>{pretty(blueprintRequirements)}</pre> : <p>No blueprint requirements have been compiled.</p>}
                  </section>
                  <section className="rpg-world-library-panel">
                    <p className="eyebrow">Immutable history</p>
                    <h3>Published releases</h3>
                    <div className="rpg-world-library-release-list">
                      {detail.releases.map((release) => (
                        <article key={`${release.world_revision}:${release.release}`}>
                          <strong>World r{release.world_revision} • release {release.release}</strong>
                          <span>{Boolean(certification(release).launch_ready) ? 'Certified' : 'Review required'}</span>
                          <small>{release.release_hash}</small>
                        </article>
                      ))}
                    </div>
                  </section>
                </div>

                <section className="rpg-world-library-panel">
                  <p className="eyebrow">Scenario editor</p>
                  <h3>Campaign openings</h3>
                  <div className="rpg-world-library-inline-form">
                    <label><span>Scenario id</span><input value={scenarioId} onChange={(event) => setScenarioId(event.currentTarget.value)} /></label>
                    <label><span>Title</span><input value={scenarioTitle} onChange={(event) => setScenarioTitle(event.currentTarget.value)} /></label>
                    <label><span>Starting location</span><input value={scenarioLocation} onChange={(event) => setScenarioLocation(event.currentTarget.value)} /></label>
                    <label><span>Player name</span><input value={playerName} onChange={(event) => setPlayerName(event.currentTarget.value)} /></label>
                  </div>
                  <div className="rpg-world-library-actions">
                    <button type="button" disabled={createScenarioMutation.isPending} onClick={() => createScenarioMutation.mutate()}>Create scenario</button>
                    <button
                      type="button"
                      disabled={!latestRevision || !latestRelease || publishScenarioMutation.isPending}
                      onClick={() => latestRevision && latestRelease && publishScenarioMutation.mutate({
                        scenarioId,
                        worldRevision: latestRevision.revision,
                        worldRevisionHash: latestRevision.content_hash,
                        compatibleRelease: latestRelease.release,
                      })}
                    >Publish scenario revision</button>
                  </div>
                  <div className="rpg-world-library-scenario-list">
                    {worldScenarios.map((scenario) => {
                      const revisions = detail.scenario_revisions[scenario.id] ?? [];
                      return (
                        <article key={scenario.id}>
                          <div><strong>{scenario.title}</strong><span>{scenario.status} • {revisions.length} revisions</span></div>
                          {revisions.map((scenarioRevision) => {
                            const release = matchingRelease(detail, scenarioRevision);
                            const ready = Boolean(certification(release).launch_ready);
                            return (
                              <div className="rpg-world-library-scenario-revision" key={scenarioRevision.revision}>
                                <span>r{scenarioRevision.revision} • world r{scenarioRevision.world_revision}</span>
                                <button
                                  type="button"
                                  disabled={!release || !ready || launchMutation.isPending}
                                  onClick={() => release && launchMutation.mutate({
                                    scenarioId: scenario.id,
                                    scenarioRevision: scenarioRevision.revision,
                                    worldRevision: scenarioRevision.world_revision,
                                    worldRelease: release.release,
                                  })}
                                >{ready ? 'Launch campaign' : 'Not certified'}</button>
                              </div>
                            );
                          })}
                        </article>
                      );
                    })}
                  </div>
                </section>
              </>
            ) : null}
          </main>
        </div>
      )}
    </section>
  );
}
