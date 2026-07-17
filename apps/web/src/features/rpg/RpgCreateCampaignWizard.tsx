import { useEffect, useMemo, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import type { RpgLaunchResponse, RpgNewGameRequest } from '../../api/client';
import {
  rpgWorldLibraryClient,
  type RpgScenarioRevision,
  type RpgScenarioSummary,
  type RpgWorldRelease,
  type RpgWorldSummary,
} from '../../api/rpgWorldLibraryClient';
import { loadSettingsProfile } from '../settings/settingsApi';
import { RpgCreateCampaignWizard as LegacyRpgCreateCampaignWizard } from './RpgCreateCampaignWizardLegacy';
import { applyRpgWizardDefaults, rpgWizardDefaultsFromSettings } from './rpgWizardDefaults';

interface RpgCreateCampaignWizardProps {
  onCreateCampaign?: (request: RpgNewGameRequest) => Promise<RpgLaunchResponse>;
  onEnterWorld?: () => void;
}

const RPG_SELECTED_SESSION_STORAGE_KEY = 'omnix:rpg:selected-session-id';

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function number(value: unknown, fallback = 0): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback;
}

function latestScenarioRevision(revisions: RpgScenarioRevision[]): RpgScenarioRevision | undefined {
  return [...revisions].sort((left, right) => right.revision - left.revision)[0];
}

function matchingRelease(
  releases: RpgWorldRelease[],
  scenarioRevision: RpgScenarioRevision | undefined,
): RpgWorldRelease | undefined {
  if (!scenarioRevision) return undefined;
  const compatibleRelease = number(record(scenarioRevision.document).compatible_release);
  return releases.find((release) => (
    release.world_revision === scenarioRevision.world_revision
    && (!compatibleRelease || release.release === compatibleRelease)
  ));
}

function releaseIsLaunchReady(release: RpgWorldRelease | undefined): boolean {
  return Boolean(record(record(release?.document).certification).launch_ready);
}

function worldLabel(world: RpgWorldSummary): string {
  const scenarios = world.scenario_count ?? 0;
  return `${world.title} · ${scenarios} published opening${scenarios === 1 ? '' : 's'}`;
}

function scenarioLabel(scenario: RpgScenarioSummary): string {
  return `${scenario.title}${scenario.description ? ` · ${scenario.description}` : ''}`;
}

export function RpgCreateCampaignWizard(props: RpgCreateCampaignWizardProps) {
  const rootRef = useRef<HTMLDivElement | null>(null);
  const touchedRef = useRef(false);
  const applyingRef = useRef(false);
  const [selectedWorldId, setSelectedWorldId] = useState('');
  const [selectedScenarioId, setSelectedScenarioId] = useState('');
  const [launchedSessionId, setLaunchedSessionId] = useState('');

  const libraryQuery = useQuery({
    queryKey: ['feature', 'rpg', 'world-library', 'campaign-wizard'],
    queryFn: () => rpgWorldLibraryClient.list(),
  });
  const availableWorlds = useMemo(
    () => (libraryQuery.data?.worlds ?? []).filter((world) => world.status !== 'archived'),
    [libraryQuery.data?.worlds],
  );
  const selectedWorld = availableWorlds.find((world) => world.id === selectedWorldId);
  const detailQuery = useQuery({
    queryKey: ['feature', 'rpg', 'world-library', 'campaign-wizard', selectedWorldId],
    queryFn: () => rpgWorldLibraryClient.detail(selectedWorldId),
    enabled: Boolean(selectedWorldId),
  });

  useEffect(() => {
    if (!selectedWorldId && availableWorlds[0]?.id) {
      setSelectedWorldId(availableWorlds[0].id);
    }
  }, [availableWorlds, selectedWorldId]);

  const publishedScenarios = useMemo(
    () => (detailQuery.data?.scenarios ?? []).filter((scenario) => (
      scenario.status === 'published'
      && Boolean(detailQuery.data?.scenario_revisions[scenario.id]?.length)
    )),
    [detailQuery.data],
  );

  useEffect(() => {
    if (!publishedScenarios.some((scenario) => scenario.id === selectedScenarioId)) {
      setSelectedScenarioId(publishedScenarios[0]?.id ?? '');
    }
  }, [publishedScenarios, selectedScenarioId]);

  useEffect(() => {
    let active = true;
    loadSettingsProfile()
      .then(({ profile }) => {
        if (!active || touchedRef.current || !rootRef.current) return;
        applyingRef.current = true;
        try {
          applyRpgWizardDefaults(rootRef.current, rpgWizardDefaultsFromSettings(profile));
        } finally {
          applyingRef.current = false;
        }
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, []);

  const selectedScenario = publishedScenarios.find((scenario) => scenario.id === selectedScenarioId);
  const selectedScenarioRevision = latestScenarioRevision(
    detailQuery.data?.scenario_revisions[selectedScenarioId] ?? [],
  );
  const selectedRelease = matchingRelease(detailQuery.data?.releases ?? [], selectedScenarioRevision);
  const launchReady = Boolean(
    selectedWorld
    && selectedScenario
    && selectedScenarioRevision
    && selectedRelease
    && releaseIsLaunchReady(selectedRelease),
  );

  const markTouched = () => {
    if (!applyingRef.current) touchedRef.current = true;
  };

  const launchExistingCampaign = async (request: RpgNewGameRequest): Promise<RpgLaunchResponse> => {
    if (!selectedWorld || !selectedScenario || !selectedScenarioRevision || !selectedRelease) {
      throw new Error('Select an existing world with a published scenario before starting a campaign.');
    }
    if (!releaseIsLaunchReady(selectedRelease)) {
      throw new Error('The selected world release is not certified as launch ready.');
    }

    const result = await rpgWorldLibraryClient.launchScenario(
      selectedScenario.id,
      selectedScenarioRevision.revision,
      {
        world_id: selectedWorld.id,
        world_revision: selectedScenarioRevision.world_revision,
        world_release: selectedRelease.release,
        player: request.player ?? {},
        gameplay: {
          campaign_template: request.campaign_template,
          genre: request.genre,
          tone: request.tone,
          background: request.background,
          primary_capability: request.primary_capability,
          secondary_capabilities: request.secondary_capabilities,
          power_source: request.power_source,
          generated_class_name: request.generated_class_name,
          generated_class_summary: request.generated_class_summary,
          difficulty: request.difficulty,
          world_activity: request.world_activity,
          economy_pressure: request.economy_pressure,
          combat_lethality: request.combat_lethality,
          companions_enabled: request.companions_enabled,
          permadeath: request.permadeath,
          seed: request.seed,
          initial_stats: request.initial_stats,
          genesis: request.genesis,
        },
        features: request.features ?? {},
      },
    );

    if (!result.ok || !result.session_id) {
      throw new Error(result.error ?? 'The selected published scenario did not return a campaign session.');
    }

    setLaunchedSessionId(result.session_id);
    try {
      window.localStorage.setItem(RPG_SELECTED_SESSION_STORAGE_KEY, result.session_id);
    } catch {
      // Entering the world still works when storage is unavailable; reload will refresh the session inventory.
    }

    return {
      ok: true,
      session_id: result.session_id,
      status: result.status ?? 'ready',
      session: result.session,
      game: result.game,
    };
  };

  const enterExistingWorld = () => {
    props.onEnterWorld?.();
    if (launchedSessionId) window.location.reload();
  };

  const sourceStatus = libraryQuery.isError
    ? 'Unable to load reusable worlds.'
    : !availableWorlds.length && !libraryQuery.isPending
      ? 'Create or import a world in Worlds & Campaigns before starting a campaign.'
      : detailQuery.isPending
        ? 'Loading published scenarios and immutable releases…'
        : !publishedScenarios.length
          ? 'This world has no published scenario. Publish an opening before starting a campaign.'
          : launchReady
            ? `Ready: ${selectedWorld?.title} · ${selectedScenario?.title}`
            : 'The selected scenario does not have a launch-ready certified release.';

  return (
    <div ref={rootRef} style={{ display: 'contents' }} onChangeCapture={markTouched} onInputCapture={markTouched}>
      <section
        aria-label="Existing world selection"
        style={{
          border: '1px solid var(--border-subtle, rgba(255,255,255,.12))',
          borderRadius: 14,
          padding: 14,
          marginBottom: 14,
          background: 'var(--surface-elevated, rgba(255,255,255,.035))',
        }}
      >
        <div style={{ fontWeight: 700, marginBottom: 4 }}>Campaign source</div>
        <div style={{ opacity: 0.72, fontSize: 13, marginBottom: 10 }}>
          Choose an existing reusable world and one of its published openings. New Campaign launches an immutable world release; it does not create or regenerate a world.
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 10 }}>
          <label style={{ display: 'grid', gap: 5 }}>
            <span>Existing world</span>
            <select
              aria-label="Existing world"
              value={selectedWorldId}
              disabled={libraryQuery.isPending || !availableWorlds.length}
              onChange={(event) => {
                setSelectedWorldId(event.currentTarget.value);
                setSelectedScenarioId('');
              }}
            >
              {!availableWorlds.length ? <option value="">No reusable worlds available</option> : null}
              {availableWorlds.map((world) => (
                <option key={world.id} value={world.id}>{worldLabel(world)}</option>
              ))}
            </select>
          </label>
          <label style={{ display: 'grid', gap: 5 }}>
            <span>Published scenario</span>
            <select
              aria-label="Published scenario"
              value={selectedScenarioId}
              disabled={detailQuery.isPending || !publishedScenarios.length}
              onChange={(event) => setSelectedScenarioId(event.currentTarget.value)}
            >
              {!publishedScenarios.length ? <option value="">No published openings available</option> : null}
              {publishedScenarios.map((scenario) => (
                <option key={scenario.id} value={scenario.id}>{scenarioLabel(scenario)}</option>
              ))}
            </select>
          </label>
        </div>
        <p style={{ margin: '10px 0 0', fontSize: 13, opacity: launchReady ? 0.9 : 0.72 }} aria-live="polite">
          {sourceStatus}
        </p>
      </section>
      <LegacyRpgCreateCampaignWizard
        {...props}
        onCreateCampaign={launchExistingCampaign}
        onEnterWorld={enterExistingWorld}
      />
    </div>
  );
}
