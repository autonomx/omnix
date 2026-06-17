import { Button, Progress, Text } from '@mantine/core';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { omnixApiClient } from '../../api/client';
import type { OmnixModuleDefinition } from '../../app/modules';
import { OmnixStatusPill, WorkspacePanel } from '../../design/primitives';
import { FeatureSubmitFeedback, FeatureValidationMessage } from '../shared/FeatureSubmitFeedback';
import { createRpgWorkspaceState } from './rpgUiState';
import './RpgWorkspace.css';

interface RpgFormValues {
  sessionId: string;
  command: string;
}

export function RpgWorkspace({ module }: { module: OmnixModuleDefinition }) {
  const queryClient = useQueryClient();
  const inventoryQuery = useQuery({
    queryKey: ['feature', 'rpg', 'replay-inventory'],
    queryFn: () => omnixApiClient.getReplayPersistenceInventory(),
  });
  const jobsQuery = useQuery({
    queryKey: ['platform', 'jobs'],
    queryFn: () => omnixApiClient.listJobs(),
  });
  const assetsQuery = useQuery({
    queryKey: ['platform', 'assets'],
    queryFn: () => omnixApiClient.listAssets(),
  });
  const reportsQuery = useQuery({
    queryKey: ['platform', 'reports'],
    queryFn: () => omnixApiClient.listReports(),
  });
  const {
    register,
    handleSubmit,
    reset,
    setValue,
    watch,
    formState: { errors },
  } = useForm<RpgFormValues>({
    defaultValues: { sessionId: '', command: '' },
  });
  const selectedSessionId = watch('sessionId');
  const {
    heroSummary,
    heroStats,
    equippedGear,
    partyMembers,
    activeQuests,
    quickActions,
    recentEvents,
    journalEntries,
    journalDetail,
    inventoryItems,
    hotbarAbilities,
    worldStateRows,
    npcRelationships,
    encounter,
    sessionSummaries,
    selectedSessionSummary,
    checkpointSummary,
    rpgJobs,
    rpgAssets,
    rpgReports,
    jobCards,
  } = createRpgWorkspaceState({
    inventory: inventoryQuery.data,
    jobs: jobsQuery.data,
    assets: assetsQuery.data,
    reports: reportsQuery.data,
    selectedSessionId,
  });
  const createJobMutation = useMutation({
    mutationFn: (values: RpgFormValues) =>
      omnixApiClient.createJob({
        module: 'rpg',
        type: 'rpg.turn',
        resource_class: 'gpu:llm',
        priority: 0,
        input_ref: values.sessionId ? { session_id: values.sessionId } : null,
        input_payload: {
          command: values.command,
          determinism_policy: 'replay_preserving',
        },
        stages: [
          { id: 'load-session', label: 'Load session', resource_class: 'cpu', status: 'queued' },
          { id: 'apply-turn', label: 'Apply deterministic turn', resource_class: 'cpu', status: 'queued' },
          { id: 'narrate', label: 'Generate narration', resource_class: 'gpu:llm', status: 'queued' },
          { id: 'checkpoint', label: 'Write checkpoint', resource_class: 'cpu', status: 'queued' },
        ],
      }),
    onSuccess: async (_job, values) => {
      reset({ sessionId: values.sessionId, command: '' });
      await queryClient.invalidateQueries({ queryKey: ['platform', 'jobs'] });
    },
  });
  const submitStatus = createJobMutation.isPending ? 'queueing' : createJobMutation.isError ? 'error' : createJobMutation.data?.status ?? 'ready';

  return (
    <WorkspacePanel className="rpg-workstation">
      <header className="rpg-workstation-header">
        <div>
          <p className="eyebrow">Feature module</p>
          <h2 id="module-title">{module.label} mode</h2>
          <p>{module.summary}</p>
        </div>
        <div className="rpg-header-pills" aria-label="RPG runtime status">
          <OmnixStatusPill>Engine: {submitStatus}</OmnixStatusPill>
          <OmnixStatusPill>Session: {selectedSessionSummary.title}</OmnixStatusPill>
          <OmnixStatusPill>Replay-preserving</OmnixStatusPill>
          <code>{module.route}</code>
        </div>
      </header>

      <div className="rpg-dashboard-grid">
        <aside className="rpg-left-rail" aria-label="Player, party, and quests">
          <section className="rpg-card rpg-hero-card">
            <p className="eyebrow">Your hero</p>
            <div className="rpg-hero-summary">
              <div className="rpg-avatar rpg-hero-avatar" aria-hidden="true">
                {heroSummary.avatar}
              </div>
              <div>
                <h3>{heroSummary.name}</h3>
                <p>{heroSummary.subtitle}</p>
                <p>{heroSummary.origin}</p>
              </div>
            </div>
            <div className="rpg-stat-stack">
              {heroStats.map((stat) => (
                <div className="rpg-stat-row" key={stat.label}>
                  <span>{stat.label}</span>
                  <strong>{stat.value}</strong>
                  <span className={`rpg-meter rpg-meter-${stat.tone}`} aria-label={`${stat.label} ${stat.value}`}>
                    <span style={{ width: `${stat.percent}%` }} />
                  </span>
                </div>
              ))}
            </div>
            <div className="rpg-xp-row">
              <span>XP</span>
              <span className="rpg-meter rpg-meter-xp" aria-label={`XP ${heroSummary.xpLabel}`}>
                <span style={{ width: `${heroSummary.xpPercent}%` }} />
              </span>
              <strong>{heroSummary.xpLabel}</strong>
            </div>
            <div className="rpg-resource-grid">
              <div>
                <span>Gold</span>
                <strong>{heroSummary.gold}</strong>
              </div>
              <div>
                <span>Renown</span>
                <strong>{heroSummary.renown}</strong>
              </div>
            </div>
          </section>

          <section className="rpg-card">
            <div className="rpg-section-heading">
              <p className="eyebrow">Equipped gear</p>
            </div>
            <div className="rpg-list-stack">
              {equippedGear.map((item) => (
                <article className="rpg-list-row" key={item.name}>
                  <span className="rpg-icon-tile" aria-hidden="true">
                    {item.icon}
                  </span>
                  <div>
                    <strong>{item.name}</strong>
                    <span>{item.slot}</span>
                  </div>
                </article>
              ))}
            </div>
          </section>

          <section className="rpg-card">
            <div className="rpg-section-heading">
              <p className="eyebrow">Party</p>
              <span>{partyMembers.length} / 4</span>
            </div>
            <div className="rpg-list-stack">
              {partyMembers.map((member) => (
                <article className="rpg-party-row" key={member.name}>
                  <span className="rpg-avatar rpg-avatar-small" aria-hidden="true">
                    {member.avatar}
                  </span>
                  <div>
                    <strong>{member.name}</strong>
                    <span>{member.role}</span>
                  </div>
                  <span className="rpg-party-health">
                    <span style={{ width: `${member.percent}%` }} />
                  </span>
                  <small>{member.hp}</small>
                </article>
              ))}
            </div>
            <button className="rpg-secondary-button" type="button">
              + Add companion
            </button>
          </section>

          <section className="rpg-card">
            <p className="eyebrow">Active quests</p>
            <div className="rpg-list-stack">
              {activeQuests.map((quest) => (
                <article className="rpg-quest-row" key={quest.title}>
                  <span className="rpg-quest-icon" aria-hidden="true">
                    {quest.icon}
                  </span>
                  <div>
                    <strong>{quest.title}</strong>
                    <span>{quest.detail}</span>
                  </div>
                  <span aria-hidden="true">›</span>
                </article>
              ))}
            </div>
          </section>
        </aside>

        <main className="rpg-center-stage" aria-label="Story scene and actions">
          <section className="rpg-card rpg-story-card">
            <div className="rpg-story-heading">
              <div>
                <p className="eyebrow">Story / scene</p>
                <h3>📍 {selectedSessionSummary.location}</h3>
                <div className="rpg-chip-row">
                  <span>{selectedSessionSummary.title}</span>
                  <span>{selectedSessionSummary.turnLabel}</span>
                  <span>{selectedSessionSummary.updatedAt}</span>
                </div>
              </div>
              <div className="rpg-scene-art" aria-label={`${selectedSessionSummary.location} scene preview`} />
            </div>
            <p className="rpg-scene-copy">{selectedSessionSummary.summary}</p>
            <div className="rpg-dialogue-stack">
              <article>
                <span className="rpg-avatar rpg-avatar-small">{heroSummary.avatar}</span>
                <div>
                  <strong>{heroSummary.name} (You)</strong>
                  <p>“I scan the current scene for useful details before committing to the next deterministic turn.”</p>
                </div>
              </article>
              <article>
                <span className="rpg-avatar rpg-avatar-small rpg-avatar-omnix">O</span>
                <div>
                  <strong>Omnix (Narrator)</strong>
                  <p>
                    The selected RPG session is ready. Queue a replay-preserving command to advance the simulation and update the
                    scene from the authoritative turn result.
                  </p>
                </div>
              </article>
            </div>
            <div className="rpg-event-strip">
              <strong>Recent events</strong>
              <ul>
                {recentEvents.map((event) => (
                  <li key={event}>{event}</li>
                ))}
              </ul>
            </div>
            <form className="rpg-action-composer" onSubmit={handleSubmit((values) => createJobMutation.mutate(values))}>
              <div className="rpg-action-composer-heading">
                <h3>Turn request</h3>
                <p>Queue replay-preserving RPG commands into the deterministic turn pipeline.</p>
              </div>
              <label>
                <span>Session</span>
                <select {...register('sessionId')}>
                  <option value="">New or current session</option>
                  {sessionSummaries.map((session) => (
                    <option key={session.id} value={session.id}>
                      {session.title === session.id ? session.id : `${session.title} — ${session.id}`}
                    </option>
                  ))}
                </select>
              </label>
              <label className="rpg-command-field">
                <span>Command</span>
                <textarea
                  rows={3}
                  aria-invalid={Boolean(errors.command)}
                  placeholder="What do you want to do?"
                  {...register('command', { required: true })}
                />
              </label>
              <Button className="rpg-submit-button" type="submit" disabled={createJobMutation.isPending} loading={createJobMutation.isPending}>
                {createJobMutation.isPending ? 'Queueing…' : 'Queue RPG turn'}
              </Button>
            </form>
            <FeatureValidationMessage show={Boolean(errors.command)} message="Enter a command before queueing an RPG turn." />
            <FeatureSubmitFeedback
              error={createJobMutation.error}
              errorPrefix="RPG turn request"
              isError={createJobMutation.isError}
              isPending={createJobMutation.isPending}
              jobId={createJobMutation.data?.id}
              pendingMessage="Queueing RPG turn job…"
              successPrefix="RPG turn job queued"
            />
            <div className="rpg-quick-actions" aria-label="Quick RPG actions">
              {quickActions.map((action) => (
                <button
                  key={action.label}
                  type="button"
                  onClick={() => setValue('command', action.command, { shouldDirty: true, shouldValidate: true })}
                >
                  <span aria-hidden="true">{action.icon}</span>
                  {action.label}
                </button>
              ))}
            </div>
          </section>

          <section className="rpg-card rpg-journal-card">
            <div className="rpg-tabs" role="tablist" aria-label="RPG logs">
              <button type="button" className="active" role="tab" aria-selected="true">
                Journal
              </button>
              <button type="button" role="tab" aria-selected="false">
                Dialogue log
              </button>
              <button type="button" role="tab" aria-selected="false">
                Turn history
              </button>
            </div>
            <div className="rpg-journal-grid">
              <div className="rpg-journal-list">
                {journalEntries.map((entry, index) => (
                  <article className={index === 0 ? 'active' : undefined} key={entry.title}>
                    <span aria-hidden="true" />
                    <div>
                      <strong>{entry.time}</strong>
                      <p>{entry.title}</p>
                    </div>
                  </article>
                ))}
              </div>
              <article className="rpg-journal-detail">
                <h3>{journalDetail.title}</h3>
                <p>{journalDetail.detail}</p>
                <ul>
                  {journalDetail.bullets.map((bullet) => (
                    <li key={bullet}>{bullet}</li>
                  ))}
                </ul>
                <div className="rpg-chip-row">
                  {journalDetail.tags.map((tag) => (
                    <span key={tag}>{tag}</span>
                  ))}
                </div>
              </article>
            </div>
          </section>

          <section className="rpg-card rpg-inventory-card">
            <div className="rpg-tabs" role="tablist" aria-label="Inventory tabs">
              <button type="button" className="active" role="tab" aria-selected="true">
                Inventory
              </button>
              <button type="button" role="tab" aria-selected="false">
                Abilities
              </button>
              <button type="button" role="tab" aria-selected="false">
                Hotbar
              </button>
            </div>
            <div className="rpg-inventory-grid">
              {inventoryItems.map((item) => (
                <button className="rpg-item-slot" key={item.label} type="button" aria-label={item.label}>
                  <span aria-hidden="true">{item.icon}</span>
                  <small>{item.count}</small>
                </button>
              ))}
              <button className="rpg-item-slot rpg-empty-slot" type="button" aria-label="Empty inventory slot">
                +
              </button>
              <div className="rpg-hotbar" aria-label="Ability hotbar">
                {hotbarAbilities.map((ability) => (
                  <button type="button" key={ability.key} aria-label={ability.label}>
                    <small>{ability.key}</small>
                    <span>{ability.icon}</span>
                  </button>
                ))}
              </div>
            </div>
          </section>
        </main>

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
              <span>{rpgJobs.length ? `${rpgJobs.length} live` : 'Preview'}</span>
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
                <small>{rpgReports.length ? `${rpgReports.length} ready` : 'No RPG reports found'}</small>
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
      </div>
    </WorkspacePanel>
  );
}
