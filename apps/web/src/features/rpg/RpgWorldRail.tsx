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
  checkpointSummary: RpgCheckpointSummaryPreview;
  encounter: RpgEncounterPreview;
  jobCards: RpgJobCardPreview[];
  npcRelationships: RpgNpcRelationshipPreview[];
  rpgAssets: RpgReportAssetPreview[];
  rpgJobCount: number;
  rpgReportCount: number;
  selectedSessionSummary: RpgSessionSummaryPreview;
  worldStateRows: RpgWorldStateRowPreview[];
}

export function RpgWorldRail({
  checkpointSummary,
  encounter,
  jobCards,
  npcRelationships,
  rpgAssets,
  rpgJobCount,
  rpgReportCount,
  selectedSessionSummary,
  worldStateRows,
}: RpgWorldRailProps) {
  return (
    <aside className="rpg-right-rail" aria-label="World, jobs, and reports">
      <section className="rpg-card rpg-map-card">
        <div className="rpg-section-heading">
          <p className="eyebrow">World & location</p>
          <button type="button">Change location</button>
        </div>
        <div className="rpg-map-preview" aria-label={`${selectedSessionSummary.location} travel map`}>
          <span className="rpg-map-pin" aria-hidden="true" />
          <div className="rpg-map-controls" aria-hidden="true">
            <span>+</span>
            <span>−</span>
            <span>◎</span>
          </div>
        </div>
        <strong>{selectedSessionSummary.location}</strong>
      </section>

      <section className="rpg-card rpg-world-grid-card">
        <div className="rpg-world-state">
          <p className="eyebrow">World state</p>
          {worldStateRows.map((row) => (
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
          <span>{rpgJobCount ? `${rpgJobCount} live` : 'Preview'}</span>
        </div>
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
            <small>Off</small>
          </div>
        </div>
        <div className="rpg-report-row">
          <span>▤</span>
          <div>
            <strong>Reports</strong>
            <small>{rpgReportCount ? `${rpgReportCount} ready` : 'No RPG reports found'}</small>
          </div>
        </div>
        <div className="rpg-report-row">
          <span>▣</span>
          <div>
            <strong>Checkpoint</strong>
            <small>
              {checkpointSummary.label}: {checkpointSummary.detail}
            </small>
          </div>
        </div>
        {rpgAssets.map((asset) => (
          <article className="rpg-report-row" key={String(asset.id)}>
            <span aria-hidden="true">◈</span>
            <div>
              <h3>
                {String(asset.type)} / {String(asset.module)}
              </h3>
              <small>{String(asset.storage_path ?? asset.id)}</small>
            </div>
          </article>
        ))}
        <button className="rpg-primary-button" type="button">
          Create checkpoint
        </button>
      </section>
    </aside>
  );
}
