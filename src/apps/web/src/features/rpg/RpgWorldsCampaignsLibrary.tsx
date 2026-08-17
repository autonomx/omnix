import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  rpgWorldLibraryClient,
  type RpgMapBlueprintRevision,
  type RpgScenarioRevision,
  type RpgScenarioSummary,
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

interface WorldLocationOption {
  id: string;
  label: string;
}

const DEFAULT_BLUEPRINT = {
  schema_version: 'rpg_map_blueprint_v1',
  map_id: 'map:rusty_flagon:ground_floor',
  location_id: 'rusty_flagon_tavern',
  level: 'interior',
  navigation_kind: 'square_grid',
  required_portal_ids: ['portal:front_door'],
  required_route_ids: [],
  required_spawn_point_ids: ['spawn:arrival'],
  required_zone_ids: ['zone:common_room'],
  required_object_ids: ['object:bar_counter'],
  required_hazard_ids: [],
  size_profile: 'medium',
  directives: {},
  metadata: {},
};

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

function blueprintFindingLabel(value: Record<string, unknown>): string {
  const code = text(value.code, 'semantic mismatch');
  const target = text(value.target_id);
  const scenario = text(value.scenario_id);
  return [code, target, scenario].filter(Boolean).join(' • ');
}

function worldLocationOptions(detail: RpgWorldDetailResponse | undefined): WorldLocationOption[] {
  if (!detail) return [];
  const revision = record(detail.revisions[0]?.document);
  const canonEntities = record(record(revision.canon).entities);
  const manifestEntities = record(record(revision.entity_manifest).entities);
  const entities = { ...manifestEntities, ...canonEntities };
  const ids: string[] = [];
  const seen = new Set<string>();
  const labels = new Map<string, string>();
  const add = (value: unknown, label?: unknown) => {
    const id = text(value);
    if (id && !seen.has(id)) {
      seen.add(id);
      ids.push(id);
    }
    const resolvedLabel = text(label);
    if (id && resolvedLabel && !labels.has(id)) labels.set(id, resolvedLabel);
  };

  for (const value of array(record(revision.topology).locations)) add(value);
  for (const [entityId, entity] of Object.entries(entities)) {
    const row = record(entity);
    if (text(row.kind).toLowerCase() === 'location') {
      add(entityId, text(row.name, text(row.title)));
    }
  }
  for (const requirement of array(revision.blueprint_requirements)) {
    add(record(requirement).location_id);
  }
  for (const blueprint of detail.map_blueprints) {
    add(record(blueprint.document).location_id);
  }

  // Older/provider-authored topics can contain valid location rows even when a
  // failed canon projection left the published topology empty. Keep their
  // stable location IDs selectable without permitting arbitrary free text.
  for (const topicId of ['locations', 'regions']) {
    for (const topic of detail.topics.filter((candidate) => candidate.topic_id === topicId)) {
      const content = record(topic.content);
      for (const value of [...array(content.entities), ...array(content.locations)]) {
        const row = record(value);
        const locationId = text(
          row.location_id,
          topicId === 'locations' ? text(row.id, text(row.entity_id)) : '',
        );
        add(locationId, text(row.name, text(row.title)));
      }
    }
  }

  return ids.map((id) => {
    const entity = record(entities[id]);
    const name = labels.get(id) ?? text(entity.name, text(entity.title));
    return { id, label: name ? `${name} (${id})` : id };
  });
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
  const [blueprintMapId, setBlueprintMapId] = useState(String(DEFAULT_BLUEPRINT.map_id));
  const [blueprintJson, setBlueprintJson] = useState(pretty(DEFAULT_BLUEPRINT));
  const [blueprintExpectedRevision, setBlueprintExpectedRevision] = useState(0);
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

  useEffect(() => {
    setBlueprintExpectedRevision(0);
    setBlueprintMapId(String(DEFAULT_BLUEPRINT.map_id));
    setBlueprintJson(pretty(DEFAULT_BLUEPRINT));
  }, [selectedWorldId]);

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

  const saveBlueprintMutation = useMutation({
    mutationFn: () => {
      const document = JSON.parse(blueprintJson) as Record<string, unknown>;
      return rpgWorldLibraryClient.saveMapBlueprint(
        selectedWorldId,
        blueprintMapId.trim(),
        { expected_revision: blueprintExpectedRevision, document },
      );
    },
    onSuccess: async (result) => {
      setBlueprintExpectedRevision(result.map_blueprint.blueprint_revision);
      setBlueprintJson(pretty(result.map_blueprint.document));
      setFeedback(
        result.map_blueprint.status === 'ready'
          ? `Blueprint ${result.map_blueprint.map_id} r${result.map_blueprint.blueprint_revision} is ready.`
          : `Blueprint saved with ${result.map_blueprint.findings.length} reconciliation finding(s).`,
      );
      setError(undefined);
      await refresh();
    },
    onError: (cause) => setError(cause instanceof Error ? cause.message : 'Blueprint save failed.'),
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

  const repairWorldMutation = useMutation({
    mutationFn: () => rpgWorldLibraryClient.repairWorldForLaunch(selectedWorldId, {
      scenario_id: scenarioId.trim(),
      starting_location_id: scenarioLocation,
    }),
    onSuccess: async (result) => {
      setFeedback(
        `World repaired for launch. Scenario revision ${result.scenario_revision.revision} now uses world revision ${result.scenario_revision.world_revision}.`,
      );
      setError(undefined);
      await refresh();
    },
    onError: (cause) => setError(
      cause instanceof Error ? cause.message : 'World launch repair failed.',
    ),
  });

  const worldLifecycleMutation = useMutation({
    mutationFn: (status: string) => (
      status === 'archived'
        ? rpgWorldLibraryClient.restoreWorld(selectedWorldId)
        : rpgWorldLibraryClient.archiveWorld(selectedWorldId)
    ),
    onSuccess: async (result) => {
      setFeedback(`World ${result.world.status}: ${result.world.title}`);
      setError(undefined);
      await refresh();
    },
    onError: (cause) => setError(cause instanceof Error ? cause.message : 'World lifecycle change failed.'),
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
    mutationFn: async (values: {
      scenarioId: string;
      scenarioRevision: number;
      worldRevision: number;
      worldRevisionHash: string;
      compatibleRelease: number;
    }) => {
      const publish = (
        worldRevision: number,
        worldRevisionHash: string,
        compatibleRelease: number,
      ) => rpgWorldLibraryClient.publishScenario(values.scenarioId, {
        revision: values.scenarioRevision,
        world_id: selectedWorldId,
        world_revision: worldRevision,
        world_revision_hash: worldRevisionHash,
        compatible_release: compatibleRelease,
        starting_epoch: 'Day 1',
        starting_location_id: scenarioLocation,
        activated_conflict_ids: [],
        initial_npc_ids: [],
        protagonist_options: [],
        starting_resources: {},
        opening_seed_ids: [],
        map_initialization: [],
        content_hash: '',
      });

      try {
        return {
          result: await publish(
            values.worldRevision,
            values.worldRevisionHash,
            values.compatibleRelease,
          ),
          promotedWorldRevision: undefined,
        };
      } catch (cause) {
        const message = cause instanceof Error ? cause.message : String(cause);
        if (!message.includes('scenario_starting_map_missing')) throw cause;
        const promoted = await rpgWorldLibraryClient.promoteStarterBubble(selectedWorldId, {
          source_world_revision: values.worldRevision,
          starting_location_id: scenarioLocation,
        });
        const promotion = record(promoted.promotion);
        const promotedRevision = number(promotion.world_revision);
        const promotedRelease = number(promotion.world_release);
        const promotedHash = text(promotion.world_revision_hash);
        if (!promotedRevision || !promotedRelease || !promotedHash) {
          throw new Error('Starter-map promotion did not return a publishable world release.');
        }
        return {
          result: await publish(promotedRevision, promotedHash, promotedRelease),
          promotedWorldRevision: promotedRevision,
        };
      }
    },
    onSuccess: async (result) => {
      const promotionNote = result.promotedWorldRevision
        ? ` after preparing starter maps in world revision ${result.promotedWorldRevision}`
        : '';
      setFeedback(`Scenario revision published: ${result.result.scenario_revision.revision}${promotionNote}.`);
      setError(undefined);
      await refresh();
    },
    onError: (cause) => setError(cause instanceof Error ? cause.message : 'Scenario publication failed.'),
  });

  const scenarioLifecycleMutation = useMutation({
    mutationFn: (scenario: RpgScenarioSummary) => (
      scenario.status === 'archived'
        ? rpgWorldLibraryClient.restoreScenario(scenario.id)
        : rpgWorldLibraryClient.archiveScenario(scenario.id)
    ),
    onSuccess: async (result) => {
      setFeedback(`Scenario ${result.scenario.status}: ${result.scenario.title}`);
      setError(undefined);
      await refresh();
    },
    onError: (cause) => setError(cause instanceof Error ? cause.message : 'Scenario lifecycle change failed.'),
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
  const worldArchived = selectedWorld?.status === 'archived';
  const worldScenarios = detail?.scenarios ?? [];
  const existingScenario = worldScenarios.find((scenario) => scenario.id === scenarioId.trim());
  const existingScenarioRevisions = detail?.scenario_revisions[scenarioId.trim()] ?? [];
  const latestExistingScenarioRevision = [...existingScenarioRevisions]
    .sort((left, right) => right.revision - left.revision)[0];
  const selectedScenarioRelease = detail && latestExistingScenarioRevision
    ? matchingRelease(detail, latestExistingScenarioRevision)
    : undefined;
  const selectedScenarioLaunchReady = Boolean(
    certification(selectedScenarioRelease).launch_ready,
  );
  const needsLaunchRepair = Boolean(
    existingScenario && (!latestExistingScenarioRevision || !selectedScenarioLaunchReady),
  );
  const publishedScenarioLocation = text(
    record(latestExistingScenarioRevision?.document).starting_location_id,
    text(existingScenario?.metadata.starting_location),
  );
  const locationOptions = useMemo(() => worldLocationOptions(detail), [detail]);
  const scenarioAlreadyPublished = Boolean(
    existingScenario?.status === 'published'
    && latestExistingScenarioRevision
    && publishedScenarioLocation
    && scenarioLocation === publishedScenarioLocation,
  );
  const campaignCountByWorld = useMemo(() => {
    const counts = new Map<string, number>();
    for (const campaign of libraryQuery.data?.campaigns ?? []) {
      counts.set(campaign.world_id, (counts.get(campaign.world_id) ?? 0) + 1);
    }
    return counts;
  }, [libraryQuery.data?.campaigns]);

  useEffect(() => {
    if (!locationOptions.length) {
      setScenarioLocation('');
      return;
    }
    if (!locationOptions.some((location) => location.id === scenarioLocation)) {
      const storedLocation = locationOptions.find(
        (location) => location.id === publishedScenarioLocation,
      );
      setScenarioLocation(storedLocation?.id ?? locationOptions[0].id);
    }
  }, [locationOptions, publishedScenarioLocation, scenarioLocation]);

  const loadBlueprint = (blueprint: RpgMapBlueprintRevision) => {
    setBlueprintMapId(blueprint.map_id);
    setBlueprintExpectedRevision(blueprint.blueprint_revision);
    setBlueprintJson(pretty(blueprint.document));
    setFeedback(`Loaded ${blueprint.map_id} r${blueprint.blueprint_revision} for editing.`);
    setError(undefined);
  };

  const createOrUseScenario = () => {
    if (existingScenario) {
      setError(undefined);
      setFeedback(`Using existing ${existingScenario.status} scenario: ${existingScenario.title}. Publish its next revision when ready.`);
      return;
    }
    createScenarioMutation.mutate();
  };

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
                    <button
                      type="button"
                      className="rpg-secondary-button"
                      disabled={worldLifecycleMutation.isPending}
                      onClick={() => worldLifecycleMutation.mutate(detail.world.status)}
                    >
                      {worldArchived ? 'Restore world' : 'Archive world'}
                    </button>
                  </div>
                  <dl>
                    <div><dt>Draft</dt><dd>{detail.world.draft_revision}</dd></div>
                    <div><dt>Topics</dt><dd>{detail.topics.length}</dd></div>
                    <div><dt>Blueprints</dt><dd>{detail.map_blueprints.length}</dd></div>
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
                      <button type="button" disabled={worldArchived || generationMutation.isPending} onClick={() => generationMutation.mutate()}>Generate / resume</button>
                      <button type="button" disabled={worldArchived || !latestRun || latestRun.status !== 'review' || publishGenerationMutation.isPending} onClick={() => latestRun && publishGenerationMutation.mutate(latestRun.run_id)}>Publish revision &amp; release</button>
                    </div>
                    {latestRun ? <pre>{pretty({ progress: latestRun.progress, lineage: latestRun.lineage })}</pre> : <p>No generation run yet.</p>}
                  </section>

                  <section className="rpg-world-library-panel">
                    <p className="eyebrow">Certification</p>
                    <h3>{needsLaunchRepair && launchReady ? 'Scenario pin needs repair' : launchReady ? 'Launch ready' : 'Validation findings'}</h3>
                    {validationFindings.length ? (
                      <ul>{validationFindings.map((finding) => <li key={finding}>{finding}</li>)}</ul>
                    ) : (
                      <p>{latestRelease ? 'No blocking findings in the latest release.' : 'Publish a release to calculate launch readiness.'}</p>
                    )}
                    <p>Simulation readiness and presentation readiness remain independent.</p>
                    {!launchReady || needsLaunchRepair ? (
                      <button
                        type="button"
                        disabled={worldArchived || !existingScenario || !scenarioLocation || repairWorldMutation.isPending}
                        onClick={() => repairWorldMutation.mutate()}
                      >{repairWorldMutation.isPending ? 'Repairing world…' : 'Repair world for launch'}</button>
                    ) : null}
                    {!launchReady && !existingScenario ? (
                      <small>Create or select the opening scenario before repairing its launch pin.</small>
                    ) : null}
                  </section>
                </div>

                <div className="rpg-world-library-two-column">
                  <form className="rpg-world-library-panel rpg-world-library-form" onSubmit={(event) => { event.preventDefault(); saveTopicMutation.mutate(); }}>
                    <p className="eyebrow">Manual or hybrid authoring</p>
                    <h3>World topic</h3>
                    <label><span>Topic id</span><input value={topicId} onChange={(event) => setTopicId(event.currentTarget.value)} /></label>
                    <label><span>Structured topic JSON</span><textarea rows={12} value={topicJson} onChange={(event) => setTopicJson(event.currentTarget.value)} /></label>
                    <button type="submit" disabled={worldArchived || saveTopicMutation.isPending}>Save topic draft</button>
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
                  <form className="rpg-world-library-panel rpg-world-library-form" onSubmit={(event) => { event.preventDefault(); saveBlueprintMutation.mutate(); }}>
                    <p className="eyebrow">Spatial authoring</p>
                    <h3>Map-blueprint requirements</h3>
                    <label><span>Map id</span><input value={blueprintMapId} onChange={(event) => setBlueprintMapId(event.currentTarget.value)} /></label>
                    <label><span>Expected revision</span><input type="number" min={0} value={blueprintExpectedRevision} onChange={(event) => setBlueprintExpectedRevision(Number(event.currentTarget.value))} /></label>
                    <label><span>Structured blueprint JSON</span><textarea rows={16} value={blueprintJson} onChange={(event) => setBlueprintJson(event.currentTarget.value)} /></label>
                    <button type="submit" disabled={worldArchived || saveBlueprintMutation.isPending}>Save blueprint revision</button>
                    {blueprintRequirements.length ? <details><summary>Published requirements</summary><pre>{pretty(blueprintRequirements)}</pre></details> : null}
                  </form>

                  <section className="rpg-world-library-panel">
                    <p className="eyebrow">Semantic reconciliation</p>
                    <h3>Blueprint revisions</h3>
                    <div className="rpg-world-library-topic-list">
                      {detail.map_blueprints.map((blueprint) => (
                        <article key={`${blueprint.map_id}:${blueprint.blueprint_revision}`}>
                          <strong>{blueprint.map_id} r{blueprint.blueprint_revision}</strong>
                          <span>{blueprint.status} • {blueprint.findings.length} finding(s)</span>
                          <small>{blueprint.semantic_interface_hash}</small>
                          {blueprint.findings.length ? (
                            <ul>{blueprint.findings.map((finding, index) => <li key={`${blueprint.map_id}:${index}`}>{blueprintFindingLabel(finding)}</li>)}</ul>
                          ) : <p>All active scenario semantic references reconcile.</p>}
                          <button type="button" className="rpg-secondary-button" onClick={() => loadBlueprint(blueprint)}>Edit next revision</button>
                        </article>
                      ))}
                      {!detail.map_blueprints.length ? <p>No authored blueprint revisions yet.</p> : null}
                    </div>
                  </section>
                </div>

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

                <section className="rpg-world-library-panel">
                  <p className="eyebrow">Scenario editor</p>
                  <h3>Campaign openings</h3>
                  <div className="rpg-world-library-inline-form">
                    <label><span>Scenario id</span><input value={scenarioId} onChange={(event) => setScenarioId(event.currentTarget.value)} /></label>
                    <label><span>Title</span><input value={scenarioTitle} onChange={(event) => setScenarioTitle(event.currentTarget.value)} /></label>
                    <label>
                      <span>Starting location</span>
                      <select
                        value={scenarioLocation}
                        disabled={!locationOptions.length}
                        onChange={(event) => setScenarioLocation(event.currentTarget.value)}
                      >
                        {!locationOptions.length ? <option value="">Generate or publish world locations first</option> : null}
                        {locationOptions.map((location) => (
                          <option key={location.id} value={location.id}>{location.label}</option>
                        ))}
                      </select>
                    </label>
                    <label><span>Player name</span><input value={playerName} onChange={(event) => setPlayerName(event.currentTarget.value)} /></label>
                  </div>
                  <div className="rpg-world-library-actions">
                    <button type="button" disabled={worldArchived || !scenarioLocation || createScenarioMutation.isPending} onClick={createOrUseScenario}>
                      {existingScenario ? 'Use existing scenario' : 'Create scenario'}
                    </button>
                    <button
                      type="button"
                      disabled={worldArchived || !scenarioLocation || !latestRevision || !latestRelease || scenarioAlreadyPublished || publishScenarioMutation.isPending}
                      onClick={() => latestRevision && latestRelease && publishScenarioMutation.mutate({
                        scenarioId,
                        scenarioRevision: Math.max(
                          0,
                          ...(detail.scenario_revisions[scenarioId] ?? []).map((revision) => revision.revision),
                        ) + 1,
                        worldRevision: latestRevision.revision,
                        worldRevisionHash: latestRevision.content_hash,
                        compatibleRelease: latestRelease.release,
                      })}
                    >{scenarioAlreadyPublished ? 'Scenario already published' : latestExistingScenarioRevision ? 'Publish new scenario revision' : 'Publish scenario revision'}</button>
                  </div>
                  <div className="rpg-world-library-scenario-list">
                    {worldScenarios.map((scenario) => {
                      const revisions = detail.scenario_revisions[scenario.id] ?? [];
                      const latestScenarioRevision = revisions[0];
                      const release = latestScenarioRevision ? matchingRelease(detail, latestScenarioRevision) : undefined;
                      const releaseReady = Boolean(certification(release).launch_ready);
                      return (
                        <article key={scenario.id}>
                          <div>
                            <strong>{scenario.title}</strong>
                            <span>{scenario.status} • {revisions.length} revision(s)</span>
                            <small>{latestScenarioRevision ? `World r${latestScenarioRevision.world_revision}` : 'Not published'}</small>
                          </div>
                          <div className="rpg-world-library-actions">
                            <button
                              type="button"
                              className="rpg-secondary-button"
                              disabled={scenarioLifecycleMutation.isPending}
                              onClick={() => scenarioLifecycleMutation.mutate(scenario)}
                            >
                              {scenario.status === 'archived' ? 'Restore scenario' : 'Archive scenario'}
                            </button>
                            <button
                              type="button"
                              disabled={scenario.status === 'archived' || !latestScenarioRevision || !release || !releaseReady || launchMutation.isPending}
                              onClick={() => latestScenarioRevision && release && launchMutation.mutate({
                                scenarioId: scenario.id,
                                scenarioRevision: latestScenarioRevision.revision,
                                worldRevision: latestScenarioRevision.world_revision,
                                worldRelease: release.release,
                              })}
                            >Launch campaign</button>
                          </div>
                        </article>
                      );
                    })}
                    {!worldScenarios.length ? <p>No scenarios yet.</p> : null}
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
