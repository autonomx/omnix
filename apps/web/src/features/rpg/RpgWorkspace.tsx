import { Button, Progress, Text } from '@mantine/core';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { omnixApiClient } from '../../api/client';
import type { OmnixModuleDefinition } from '../../app/modules';
import { OmnixStatusPill, WorkspacePanel } from '../../design/primitives';
import { FeatureSubmitFeedback, FeatureValidationMessage } from '../shared/FeatureSubmitFeedback';
import './RpgWorkspace.css';

interface RpgFormValues {
  sessionId: string;
  command: string;
}

interface PreviewJobCard {
  id: string;
  title: string;
  status: string;
  progress: number;
  detail: string;
  source: 'live' | 'preview';
}

const heroStats = [
  { label: 'HP', value: '86 / 110', percent: 78, tone: 'danger' },
  { label: 'Stamina', value: '72 / 100', percent: 72, tone: 'success' },
  { label: 'Mana', value: '64 / 120', percent: 53, tone: 'mana' },
];

const equippedGear = [
  { icon: '🏹', name: 'Longbow of the Boreal Wind', slot: 'Weapon' },
  { icon: '🛡️', name: 'Shadow Leather Armor +2', slot: 'Armor' },
  { icon: '🦉', name: 'Cloak of the Owl', slot: 'Cloak' },
  { icon: '💍', name: 'Band of Keen Senses', slot: 'Ring' },
];

const partyMembers = [
  { avatar: 'T', name: 'Thorin Ironfist', role: 'Lv. 14 Warrior', hp: '112 / 140', percent: 80 },
  { avatar: 'E', name: 'Elandra', role: 'Lv. 13 Mage', hp: '78 / 90', percent: 87 },
  { avatar: 'K', name: 'Kael', role: 'Lv. 12 Rogue', hp: '68 / 85', percent: 80 },
];

const activeQuests = [
  { icon: '◆', title: 'The Frostbound Relic', detail: 'Find the relic in Glimmerdeep.' },
  { icon: '▲', title: 'Secrets in the Snow', detail: 'Investigate the old watchtower.' },
  { icon: '⬟', title: 'Bounty: Icefang Alpha', detail: 'Track down the alpha beast.' },
];

const quickActions = [
  { label: 'Talk', icon: '☯', command: 'Talk to Thorin about the tracks near the archway.' },
  { label: 'Travel', icon: '🧭', command: 'Travel deeper into Glimmerdeep Pass toward the watchtower.' },
  { label: 'Investigate', icon: '⌕', command: 'Investigate the clawed tracks and torn Northern Watch banner.' },
  { label: 'Rest', icon: '♨', command: 'Make a short camp and let the party recover.' },
  { label: 'Inventory', icon: '▣', command: 'Open inventory and check supplies before moving on.' },
  { label: 'Attack', icon: '⚔', command: 'Prepare an ambush in case Icefang scouts are nearby.' },
];

const recentEvents = [
  'You arrived at Glimmerdeep Pass.',
  'Thorin Ironfist: “Best keep our eyes open. This place gives me the chills.”',
  'You gained 120 XP.',
];

const journalEntries = [
  { time: 'Day 18 • 09:42', title: 'Arrived at Glimmerdeep Pass', detail: 'Reached the ancient archway.' },
  { time: 'Day 18 • 08:15', title: 'Left Frostpine Hollow', detail: 'Followed the northern trail.' },
  { time: 'Day 17 • 21:30', title: 'Long Rest at Frostpine', detail: 'Recovered after the Icefang fight.' },
];

const inventoryItems = [
  { icon: '🧪', count: '12', label: 'Healing potion' },
  { icon: '💧', count: '7', label: 'Mana tonic' },
  { icon: '🥩', count: '5', label: 'Trail rations' },
  { icon: '🔮', count: '3', label: 'Focus crystal' },
  { icon: '🪢', count: '2', label: 'Rope coil' },
  { icon: '🔥', count: '9', label: 'Torch' },
  { icon: '🍃', count: '4', label: 'Keenleaf' },
  { icon: '📜', count: '6', label: 'Scroll' },
];

const hotbarAbilities = [
  { key: '1', icon: '✦', label: 'Aimed Shot' },
  { key: '2', icon: '↯', label: 'Frost Arrow' },
  { key: '3', icon: '☘', label: 'Camouflage' },
  { key: '4', icon: '✹', label: 'Radiant Flare' },
  { key: '5', icon: '⟡', label: 'Volley' },
  { key: '6', icon: '⇥', label: 'Dash' },
];

const worldStateRows = [
  { icon: '☀', label: 'Time', value: 'Day 18 • 09:42' },
  { icon: '≋', label: 'Weather', value: 'Cold, Windy' },
  { icon: '❄', label: 'Temperature', value: '-12°C' },
  { icon: '✦', label: 'Reputation', value: 'Honored (35)' },
];

const npcRelationships = [
  { name: 'Thorin Ironfist', stance: 'Ally', score: 78 },
  { name: 'Elandra', stance: 'Ally', score: 64 },
  { name: 'Kael', stance: 'Ally', score: 52 },
  { name: 'Captain Bryn', stance: 'Neutral', score: 10 },
];

const previewJobs: PreviewJobCard[] = [
  { id: 'preview-turn', title: 'rpg.turn', status: 'Running', progress: 68, detail: 'Load / Apply turn / Narrate / Checkpoint', source: 'preview' },
  { id: 'preview-narration', title: 'narration.generate', status: 'Running', progress: 42, detail: 'Generating presentation text', source: 'preview' },
  { id: 'preview-world', title: 'world.state.update', status: 'Queued', progress: 0, detail: 'Waiting for turn output', source: 'preview' },
];

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
    formState: { errors },
  } = useForm<RpgFormValues>({
    defaultValues: { sessionId: '', command: '' },
  });
  const sessions = inventoryQuery.data?.sessions ?? [];
  const rpgJobs = jobsQuery.data?.jobs.filter((job) => job.module === 'rpg') ?? [];
  const rpgAssets =
    assetsQuery.data?.assets.filter((asset) => asset.type === 'rpg_checkpoint' || asset.module === 'rpg') ?? [];
  const rpgReports = reportsQuery.data?.reports?.filter((report) => report.kind.includes('rpg') || report.id.includes('rpg')) ?? [];
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
  const jobCards: PreviewJobCard[] = rpgJobs.length
    ? rpgJobs.map((job) => ({
        id: String(job.id),
        title: String(job.type),
        status: String(job.status),
        progress: progressPercent(job.progress),
        detail: job.stages?.map((stage) => stage.label).join(' / ') || String(job.resource_class),
        source: 'live' as const,
      }))
    : previewJobs;

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
                A
              </div>
              <div>
                <h3>Alyndra</h3>
                <p>Level 14 • Ranger</p>
                <p>Wanderer of the North</p>
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
              <span className="rpg-meter rpg-meter-xp" aria-label="XP 7,450 of 12,000">
                <span style={{ width: '62%' }} />
              </span>
              <strong>7,450 / 12,000</strong>
            </div>
            <div className="rpg-resource-grid">
              <div>
                <span>Gold</span>
                <strong>1,248</strong>
              </div>
              <div>
                <span>Renown</span>
                <strong>Honored (35)</strong>
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
              <span>3 / 4</span>
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
                <h3>📍 Glimmerdeep Pass</h3>
                <div className="rpg-chip-row">
                  <span>Mountain Pass</span>
                  <span>Cold • Windy</span>
                  <span>Day 18 • 09:42</span>
                </div>
              </div>
              <div className="rpg-scene-art" aria-label="Snowy mountain pass scene preview" />
            </div>
            <p className="rpg-scene-copy">
              The mountain winds howl through the narrow pass, carrying the scent of pine and snow. Jagged cliffs rise on both
              sides, and an ancient stone archway stands ahead, half-buried in drifts.
            </p>
            <div className="rpg-dialogue-stack">
              <article>
                <span className="rpg-avatar rpg-avatar-small">A</span>
                <div>
                  <strong>Alyndra (You)</strong>
                  <p>“I scan the archway and surrounding cliffs for any signs of recent activity.”</p>
                </div>
              </article>
              <article>
                <span className="rpg-avatar rpg-avatar-small rpg-avatar-omnix">O</span>
                <div>
                  <strong>Omnix (Narrator)</strong>
                  <p>
                    Faint tracks—large, clawed, and fresh—mar the snow near the archway. A torn banner from the Northern Watch
                    flutters in the wind. Something big passed through here not long ago.
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
                  {sessions.map((session, index) => {
                    const sessionId = safeSessionId(session, index);
                    return (
                      <option key={sessionId} value={sessionId}>
                        {sessionId}
                      </option>
                    );
                  })}
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
                <h3>Arrived at Glimmerdeep Pass</h3>
                <p>The party makes its way through the winding mountain trail and reaches the ancient pass.</p>
                <ul>
                  <li>Discovered location: Glimmerdeep Pass</li>
                  <li>Weather: Cold, Windy</li>
                  <li>Detected tracks near the northern archway</li>
                </ul>
                <div className="rpg-chip-row">
                  <span>Exploration</span>
                  <span>Discovery</span>
                  <span>Travel</span>
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
            <div className="rpg-map-preview" aria-label="Glimmerdeep Pass travel map">
              <span className="rpg-map-pin" aria-hidden="true" />
              <div className="rpg-map-controls" aria-hidden="true">
                <span>+</span>
                <span>−</span>
                <span>◎</span>
              </div>
            </div>
            <strong>Glimmerdeep Pass</strong>
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
            <div className="rpg-encounter-card">
              <p className="eyebrow">Encounter</p>
              <span aria-hidden="true">⚔</span>
              <strong>No active combat</strong>
              <p>All quiet for now.</p>
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
                <small>{rpgAssets.length ? `${rpgAssets.length} indexed` : 'No RPG assets indexed'}</small>
              </div>
            </div>
            {rpgAssets.map((asset) => (
              <article className="rpg-report-row" key={String(asset.id)}>
                <span aria-hidden="true">◈</span>
                <div>
                  <h3>{String(asset.type)} / {String(asset.module)}</h3>
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

function safeSessionId(session: Record<string, unknown>, index: number): string {
  const candidate = session.session_id ?? session.id ?? session.name ?? `session:${index + 1}`;
  return String(candidate);
}

function progressPercent(progress: { current: number; total: number } | undefined): number {
  if (!progress || progress.total <= 0) {
    return 0;
  }

  return Math.min(100, Math.round((progress.current / progress.total) * 100));
}
