import { Progress, Text } from '@mantine/core';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { rpgSessionClient } from './api/rpgSessionClient';
import { rpgLocalMap } from './rpgLocalMap';
import { RpgMapDialog } from './RpgMapDialog';
import { RpgTacticalGrid } from './RpgTacticalGrid';
import type { RpgCheckpointSummaryPreview, RpgHerePreview, RpgJobCardPreview, RpgSessionSummaryPreview, RpgWorldStateRowPreview } from './rpgUiTypes';
import './RpgVisualAssets.css';
import './RpgWorldRail.css';

const MAP_ART_SRC = '/rpg/glimmerdeep-pass-map.svg';
/** The conditions that change what the hero does now; the rest are in the World panel. */
const NEAR_CONDITIONS: ReadonlySet<string> = new Set(['Weather', 'Temperature', 'Light', 'Hazards']);

interface RpgReportAssetPreview {
  id: unknown;
  module?: unknown;
  file_name?: unknown;
  type?: unknown;
}

interface RpgWorldRailProps {
  autoplayRunning: boolean;
  autoplayStatusLabel: string;
  className?: string;
  checkpointSummary: RpgCheckpointSummaryPreview;
  currentMapId?: string | null;
  /** The jobs, autoplay and assets card shows with Developer tools on. */
  developerTools?: boolean;
  here: RpgHerePreview;
  isAutoplayPending: boolean;
  isRefreshingJobs: boolean;
  jobCards: RpgJobCardPreview[];
  onRefreshJobs: () => void;
  onSelectCommand: (command: string) => void;
  onToggleAutoplay: () => void;
  rpgAssets: RpgReportAssetPreview[];
  rpgJobCount: number;
  selectedSessionSummary: RpgSessionSummaryPreview;
  worldStateRows: RpgWorldStateRowPreview[];
}

/** What the hero can act on where they stand: the map, who is here and where the paths lead. */
export function RpgWorldRail({
  autoplayRunning,
  autoplayStatusLabel,
  className,
  checkpointSummary,
  currentMapId,
  developerTools = false,
  here,
  isAutoplayPending,
  isRefreshingJobs,
  jobCards,
  onRefreshJobs,
  onSelectCommand,
  onToggleAutoplay,
  rpgAssets,
  rpgJobCount,
  selectedSessionSummary,
  worldStateRows,
}: RpgWorldRailProps) {
  const railClassName = className ? `rpg-right-rail ${className}` : 'rpg-right-rail';
  const isPreview = selectedSessionSummary.source === 'preview';
  const liveSessionQuery = useQuery({
    queryKey: ['feature', 'rpg', 'session', selectedSessionSummary.id],
    queryFn: () => rpgSessionClient.getRpgSession(selectedSessionSummary.id),
    enabled: !isPreview && Boolean(selectedSessionSummary.id.trim()),
  });
  const sessionRecord = recordValue(liveSessionQuery.data?.session);
  const stateRecord = recordValue(sessionRecord.state);
  const mapStateRecord = recordValue(stateRecord.map_state);
  const queriedMapId = typeof mapStateRecord.current_map_id === 'string' ? mapStateRecord.current_map_id.trim() : '';
  const activeMapId = currentMapId?.trim() || queriedMapId;
  const visibleJobCards = jobCards.slice(0, 3);
  const visibleAssets = rpgAssets.slice(0, 3);
  const { heroName, mapInstanceId, playerActorId } = rpgLocalMap(sessionRecord, selectedSessionSummary.id);
  const canOpenLiveMap = !isPreview && Boolean(selectedSessionSummary.id.trim() && (activeMapId || mapInstanceId));
  const [isMapOpen, setIsMapOpen] = useState(false);
  const conditions = worldStateRows.filter((row) => NEAR_CONDITIONS.has(row.label));

  return (
    <>
      <aside className={railClassName} aria-label="World and places">
        <section className="rpg-card rpg-map-card" aria-label="Map">
          <div role="img" className={isPreview ? 'rpg-map-preview rpg-map-preview-has-image' : mapInstanceId ? 'rpg-map-preview rpg-map-preview-has-grid' : 'rpg-map-preview'} aria-label={`${selectedSessionSummary.location} travel map`}>
            {isPreview ? (
              <img className="rpg-map-image" src={MAP_ART_SRC} alt="" aria-hidden="true" loading="lazy" />
            ) : mapInstanceId ? (
              <RpgTacticalGrid compact heroName={heroName} mapInstanceId={mapInstanceId} playerActorId={playerActorId} />
            ) : (
              <span className="rpg-live-visual-label">{activeMapId ? 'Region map ready' : 'No map for this place yet'}</span>
            )}
            {isPreview || !mapInstanceId ? <span className="rpg-map-pin" aria-hidden="true" /> : null}
          </div>
          <button className="rpg-secondary-button" disabled={!canOpenLiveMap} onClick={() => setIsMapOpen(true)} type="button">
            Open interactive map
          </button>
        </section>

        <section className="rpg-card rpg-here-card" aria-label="Here">
          <p className="eyebrow">Here</p>
          {here.people.length ? (
            <div role="group" className="rpg-here-list" aria-label="People here">
              {here.people.map((name) => (
                <button key={name} onClick={() => onSelectCommand(`I talk to ${name}.`)} title={`Talk to ${name}`} type="button">
                  {name}
                </button>
              ))}
            </div>
          ) : <p className="rpg-here-empty">No one else is here.</p>}
          {here.exits.length ? (
            <>
              <p className="eyebrow">Paths</p>
              <div role="group" className="rpg-here-list" aria-label="Paths from here">
                {here.exits.map((name) => (
                  <button key={name} onClick={() => onSelectCommand(`go to ${name}`)} title={`Go to ${name}`} type="button">
                    {name}
                  </button>
                ))}
              </div>
            </>
          ) : null}
          {conditions.length ? (
            <dl className="rpg-here-conditions">
              {conditions.map((row) => (
                <div className={row.label === 'Hazards' ? 'is-hazard' : undefined} key={row.label}>
                  <dt>{row.label}</dt>
                  <dd>{row.value}</dd>
                </div>
              ))}
            </dl>
          ) : null}
        </section>

        {developerTools ? (
        <section className="rpg-card rpg-jobs-card">
          <div className="rpg-section-heading">
            <p className="eyebrow">RPG jobs</p>
            <button type="button" onClick={onRefreshJobs} disabled={isRefreshingJobs}>
              {isRefreshingJobs ? 'Refreshing…' : 'Refresh RPG jobs'}
            </button>
          </div>
          <span>{rpgJobCount ? `${rpgJobCount} live` : isPreview ? 'Preview' : 'No active RPG jobs'}</span>
          <div className="rpg-list-stack">
            {visibleJobCards.length ? (
              visibleJobCards.map((job) => (
                <article className="rpg-job-row" key={job.id}>
                  <div>
                    <strong>{job.title}</strong>
                    <small>{job.source === 'live' ? job.status : `${job.status} preview`}</small>
                  </div>
                  <Progress value={job.progress} aria-label={`${job.title} progress`} />
                  <Text size="xs">{job.detail}</Text>
                  {job.errorDetail ? <Text className="rpg-job-error" size="xs">Reason: {job.errorDetail}</Text> : null}
                </article>
              ))
            ) : (
              <p className="rpg-empty-state">No RPG jobs are currently queued or running.</p>
            )}
          </div>
          <div role="group" className="rpg-survival-actions" aria-label="RPG runtime tools">
            <button className="rpg-secondary-button" type="button" onClick={onToggleAutoplay} disabled={isAutoplayPending}>
              {isAutoplayPending ? 'Updating autoplay…' : autoplayRunning ? 'Stop autoplay' : 'Start autoplay'}
            </button>
          </div>
          <small>{autoplayStatusLabel} · {checkpointSummary.label}: {checkpointSummary.detail}</small>
          {visibleAssets.map((asset) => (
            <article className="rpg-job-row" key={String(asset.id)}>
              <div>
                <h3>{String(asset.type)} / {String(asset.module)}</h3>
                <small>{String(asset.file_name || asset.id)}</small>
              </div>
            </article>
          ))}
        </section>
        ) : null}
      </aside>
      {canOpenLiveMap ? (
        <RpgMapDialog
          heroName={heroName}
          locationLabel={selectedSessionSummary.location}
          mapId={activeMapId}
          mapInstanceId={mapInstanceId}
          playerActorId={playerActorId}
          onClose={() => setIsMapOpen(false)}
          open={isMapOpen}
          sessionId={selectedSessionSummary.id}
        />
      ) : null}
    </>
  );
}

function recordValue(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
}
