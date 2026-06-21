import { Progress, Text } from '@mantine/core';
import type {
  RpgCheckpointSummaryPreview,
  RpgEncounterPreview,
  RpgJobCardPreview,
  RpgNpcRelationshipPreview,
  RpgSessionSummaryPreview,
  RpgWorldStateRowPreview,
} from './rpgUiState';

interface RpgReportAssetPreview {
  id: unknown;
  module?: unknown;
  storage_path?: unknown;
  type?: unknown;
}

interface RpgWorldRailProps {
  autoplayRunning: boolean;
  autoplayStatusLabel: string;
  className?: string;
  checkpointControlStatus?: string;
  checkpointSummary: RpgCheckpointSummaryPreview;
  encounter: RpgEncounterPreview;
  isAutoplayPending: boolean;
  isCreatingCheckpoint: boolean;
  isRefreshingJobs: boolean;
  jobCards: RpgJobCardPreview[];
  npcRelationships: RpgNpcRelationshipPreview[];
  onCreateCheckpoint: () => void;
  onRefreshJobs: () => void;
  onToggleAutoplay: () => void;
  reportsHref: string;
  rpgAssets: RpgReportAssetPreview[];
  rpgJobCount: number;
  rpgReportCount: number;
  selectedSessionSummary: RpgSessionSummaryPreview;
  worldStateRows: RpgWorldStateRowPreview[];
}

export function RpgWorldRail({
  autoplayRunning,
  autoplayStatusLabel,
  className,
  checkpointControlStatus,
  checkpointSummary,
  encounter,
  isAutoplayPending,
  isCreatingCheckpoint,
  isRefreshingJobs,
  jobCards,
  npcRelationships,
  onCreateCheckpoint,
  onRefreshJobs,
  onToggleAutoplay,
  reportsHref,
  rpgAssets,
  rpgJobCount,
  rpgReportCount,
  selectedSessionSummary,
  worldStateRows,
}: RpgWorldRailProps) {
  const railClassName = className ? `rpg-right-rail ${className}` : 'rpg-right-rail';
  const displayedWorldStateRows = worldStateRows.map((row) => ({
    ...row,
    value: displayWorldStateValue(row, worldStateRows, selectedSessionSummary),
  }));

  return (
    <aside className={railClassName} aria-label="World, jobs, and reports">
      <section className="rpg-card rpg-map-card">
        <div className="rpg-section-heading">
          <p className="eyebrow">World & location</p>
        </div>
        <div className="rpg-location-summary" aria-label={`${selectedSessionSummary.location} current location`}>
          <strong>{selectedSessionSummary.location}</strong>
          <span>{selectedSessionSummary.turnLabel}</span>
          <small>Travel and location changes happen through story commands and resolved turns.</small>
        </div>
      </section>

      <section className="rpg-card rpg-world-grid-card">
        <div className="rpg-world-state">
          <p className="eyebrow">World state</p>
          {displayedWorldStateRows.map((row) => (
            <div className="rpg-world-state-row" key={row.label}>
              <span aria-hidden="true">{row.icon}</span>
              <span>{row.label}</span>
              <strong>{row.value}</strong>
            </div>
          ))}
        </div>
        <div className="rpg-encounter-card" aria-label={`${encounter.title} encounter state`}>
          <p className="eyebrow">Encounter</p>
          <span aria-hidden="true">{encounter.icon}</span>
          <strong>{encounter.title}</strong>
          <p>{encounter.detail}</p>
          <small>{encounter.source === 'live' ? 'Live encounter state' : 'Preview encounter state'}</small>
        </div>
      </section>

      <section className="rpg-card">
        <p className="eyebrow">NPC relationships</p>
        <div className="rpg-list-stack">
          {npcRelationships.map((npc) => (
            <article className="rpg-relationship-row" key={npc.name}>
              <span className="rpg-avatar rpg-avatar-small" aria-hidden="true">
                {npc.name[0]}
              </span>
              <strong>{npc.name}</strong>
              <small>{npc.stance}</small>
              <span className="rpg-party-health">
                <span style={{ width: `${npc.score}%` }} />
              </span>
              <small>{npc.score}</small>
            </article>
          ))}
        </div>
      </section>

      <section className="rpg-card rpg-jobs-card">
        <div className="rpg-section-heading">
          <p className="eyebrow">RPG jobs</p>
          <button type="button" onClick={onRefreshJobs} disabled={isRefreshingJobs}>
            {isRefreshingJobs ? 'Refreshing…' : 'Refresh RPG jobs'}
          </button>
        </div>
        <span>{rpgJobCount ? `${rpgJobCount} live` : 'Preview'}</span>
        <div className="rpg-list-stack">
          {jobCards.map((job) => (
            <article className="rpg-job-row" key={job.id}>
              <div>
                <strong>{job.title}</strong>
                <small>{job.source === 'live' ? job.status : `${job.status} preview`}</small>
              </div>
              <Progress value={job.progress} aria-label={`${job.title} progress`} />
              <Text size="xs">{job.detail}</Text>
            </article>
          ))}
        </div>
      </section>

      <section className="rpg-card rpg-reports-card">
        <p className="eyebrow">Autoplay & reports</p>
        <div className="rpg-report-row">
          <span>▷</span>
          <div>
            <strong>Autoplay</strong>
            <small>{autoplayStatusLabel}</small>
            <button className="rpg-secondary-button" type="button" onClick={onToggleAutoplay} disabled={isAutoplayPending}>
              {isAutoplayPending ? 'Updating autoplay…' : autoplayRunning ? 'Stop autoplay' : 'Start autoplay'}
            </button>
          </div>
        </div>
        <div className="rpg-report-row">
          <span>▤</span>
          <div>
            <strong>Reports</strong>
            <small>{rpgReportCount ? `${rpgReportCount} ready` : 'No RPG reports found'}</small>
            <a className="rpg-secondary-button" href={reportsHref}>
              Open reports index
            </a>
          </div>
        </div>
        <div className="rpg-report-row">
          <span>▣</span>
          <div>
            <strong>Checkpoint</strong>
            <small>
              {checkpointSummary.label}: {checkpointSummary.detail}
            </small>
            {checkpointControlStatus ? <small>{checkpointControlStatus}</small> : null}
          </div>
        </div>
        {rpgAssets.length ? (
          rpgAssets.map((asset) => (
            <article className="rpg-report-row" key={String(asset.id)}>
              <span aria-hidden="true">◈</span>
              <div>
                <h3>
                  {String(asset.type)} / {String(asset.module)}
                </h3>
                <small>{String(asset.storage_path ?? asset.id)}</small>
              </div>
            </article>
          ))
        ) : (
          <article className="rpg-report-row rpg-empty-state" aria-label="No RPG artifacts">
            <span aria-hidden="true">◇</span>
            <div>
              <strong>No checkpoint/report artifacts yet</strong>
              <small>Create a checkpoint or run autoplay to produce artifact links.</small>
            </div>
          </article>
        )}
        <button className="rpg-primary-button" type="button" onClick={onCreateCheckpoint} disabled={isCreatingCheckpoint}>
          {isCreatingCheckpoint ? 'Creating checkpoint…' : 'Create checkpoint'}
        </button>
      </section>
    </aside>
  );
}

function displayWorldStateValue(
  row: RpgWorldStateRowPreview,
  rows: RpgWorldStateRowPreview[],
  selectedSessionSummary: RpgSessionSummaryPreview,
): string {
  const value = row.value.trim();
  if (row.label === 'Temperature' && isMissingWorldValue(value)) {
    const weather = rows.find((candidate) => candidate.label === 'Weather')?.value;
    return inferTemperatureLabel(weather, selectedSessionSummary.location) ?? 'Not tracked yet';
  }

  if (row.label === 'Time' && isMissingWorldValue(value)) {
    return selectedSessionSummary.turnLabel;
  }

  if ((row.label === 'Weather' || row.label === 'Reputation') && isMissingWorldValue(value)) {
    return 'Not tracked yet';
  }

  return value || 'Not tracked yet';
}

function isMissingWorldValue(value: string): boolean {
  const normalized = value.trim().toLowerCase();
  if (/\(\s*0\s*\)/.test(normalized)) {
    return false;
  }

  return !normalized || normalized === 'unknown' || normalized.includes('unknown') || normalized.includes('not tracked');
}

function inferTemperatureLabel(weather: string | undefined, location: string): string | undefined {
  const normalizedWeather = String(weather ?? '').toLowerCase();
  const normalizedLocation = location.toLowerCase();
  const source = normalizedWeather && !isMissingWorldValue(normalizedWeather) ? 'weather' : 'location';
  const text = `${normalizedWeather} ${normalizedLocation}`;

  if (/(frost|ice|snow|freez|cold|glimmerdeep|mountain)/.test(text)) {
    return `Cold (inferred from ${source})`;
  }

  if (/(rain|cloud|overcast|grey|wind|wet|tavern|market|road|quarry)/.test(text)) {
    return `Cool (inferred from ${source})`;
  }

  if (/(sun|warm|desert|heat|summer)/.test(text)) {
    return `Warm (inferred from ${source})`;
  }

  return undefined;
}
