import type { AssetListResponse, JobListResponse, PersistenceInventory, ReportListResponse } from '../../api/client';

export interface RpgStatPreview {
  label: string;
  value: string;
  percent: number;
  tone: 'danger' | 'success' | 'mana';
}

export interface RpgGearPreview {
  icon: string;
  name: string;
  slot: string;
}

export interface RpgPartyMemberPreview {
  avatar: string;
  name: string;
  role: string;
  hp: string;
  percent: number;
}

export interface RpgQuestPreview {
  icon: string;
  title: string;
  detail: string;
}

export interface RpgQuickActionPreview {
  label: string;
  icon: string;
  command: string;
}

export interface RpgJournalEntryPreview {
  time: string;
  title: string;
  detail: string;
}

export interface RpgJournalDetailPreview {
  title: string;
  detail: string;
  bullets: string[];
  tags: string[];
}

export interface RpgInventoryItemPreview {
  icon: string;
  count: string;
  label: string;
}

export interface RpgHotbarAbilityPreview {
  key: string;
  icon: string;
  label: string;
}

export interface RpgWorldStateRowPreview {
  icon: string;
  label: string;
  value: string;
}

export interface RpgNpcRelationshipPreview {
  name: string;
  stance: string;
  score: number;
}

export interface RpgJobCardPreview {
  id: string;
  title: string;
  status: string;
  progress: number;
  detail: string;
  source: 'live' | 'preview';
}

export interface RpgSessionSummaryPreview {
  id: string;
  title: string;
  location: string;
  summary: string;
  updatedAt: string;
  turnLabel: string;
  checkpointLabel: string;
  sortRank: number;
  source: 'live' | 'preview';
}

export interface RpgCheckpointSummaryPreview {
  label: string;
  detail: string;
  source: 'live' | 'preview';
}

type RpgSession = NonNullable<PersistenceInventory['sessions']>[number];
type RpgJob = JobListResponse['jobs'][number];
type RpgAsset = AssetListResponse['assets'][number];
type RpgReport = NonNullable<ReportListResponse['reports']>[number];

export interface RpgWorkspaceState {
  heroStats: RpgStatPreview[];
  equippedGear: RpgGearPreview[];
  partyMembers: RpgPartyMemberPreview[];
  activeQuests: RpgQuestPreview[];
  quickActions: RpgQuickActionPreview[];
  recentEvents: string[];
  journalEntries: RpgJournalEntryPreview[];
  journalDetail: RpgJournalDetailPreview;
  inventoryItems: RpgInventoryItemPreview[];
  hotbarAbilities: RpgHotbarAbilityPreview[];
  worldStateRows: RpgWorldStateRowPreview[];
  npcRelationships: RpgNpcRelationshipPreview[];
  sessionSummaries: RpgSessionSummaryPreview[];
  selectedSessionSummary: RpgSessionSummaryPreview;
  checkpointSummary: RpgCheckpointSummaryPreview;
  sessions: RpgSession[];
  rpgJobs: RpgJob[];
  rpgAssets: RpgAsset[];
  rpgReports: RpgReport[];
  jobCards: RpgJobCardPreview[];
}

export interface RpgWorkspaceStateSources {
  inventory?: PersistenceInventory;
  jobs?: JobListResponse;
  assets?: AssetListResponse;
  reports?: ReportListResponse;
  selectedSessionId?: string;
}

export const heroStats: RpgStatPreview[] = [
  { label: 'HP', value: '86 / 110', percent: 78, tone: 'danger' },
  { label: 'Stamina', value: '72 / 100', percent: 72, tone: 'success' },
  { label: 'Mana', value: '64 / 120', percent: 53, tone: 'mana' },
];

export const equippedGear: RpgGearPreview[] = [
  { icon: '🏹', name: 'Longbow of the Boreal Wind', slot: 'Weapon' },
  { icon: '🛡️', name: 'Shadow Leather Armor +2', slot: 'Armor' },
  { icon: '🦉', name: 'Cloak of the Owl', slot: 'Cloak' },
  { icon: '💍', name: 'Band of Keen Senses', slot: 'Ring' },
];

export const partyMembers: RpgPartyMemberPreview[] = [
  { avatar: 'T', name: 'Thorin Ironfist', role: 'Lv. 14 Warrior', hp: '112 / 140', percent: 80 },
  { avatar: 'E', name: 'Elandra', role: 'Lv. 13 Mage', hp: '78 / 90', percent: 87 },
  { avatar: 'K', name: 'Kael', role: 'Lv. 12 Rogue', hp: '68 / 85', percent: 80 },
];

export const activeQuests: RpgQuestPreview[] = [
  { icon: '◆', title: 'The Frostbound Relic', detail: 'Find the relic in Glimmerdeep.' },
  { icon: '▲', title: 'Secrets in the Snow', detail: 'Investigate the old watchtower.' },
  { icon: '⬟', title: 'Bounty: Icefang Alpha', detail: 'Track down the alpha beast.' },
];

export const quickActions: RpgQuickActionPreview[] = [
  { label: 'Talk', icon: '☯', command: 'Talk to Thorin about the tracks near the archway.' },
  { label: 'Travel', icon: '🧭', command: 'Travel deeper into Glimmerdeep Pass toward the watchtower.' },
  { label: 'Investigate', icon: '⌕', command: 'Investigate the clawed tracks and torn Northern Watch banner.' },
  { label: 'Rest', icon: '♨', command: 'Make a short camp and let the party recover.' },
  { label: 'Inventory', icon: '▣', command: 'Open inventory and check supplies before moving on.' },
  { label: 'Attack', icon: '⚔', command: 'Prepare an ambush in case Icefang scouts are nearby.' },
];

export const previewRecentEvents = [
  'You arrived at Glimmerdeep Pass.',
  'Thorin Ironfist: “Best keep our eyes open. This place gives me the chills.”',
  'You gained 120 XP.',
];

export const previewJournalEntries: RpgJournalEntryPreview[] = [
  { time: 'Day 18 • 09:42', title: 'Arrived at Glimmerdeep Pass', detail: 'Reached the ancient archway.' },
  { time: 'Day 18 • 08:15', title: 'Left Frostpine Hollow', detail: 'Followed the northern trail.' },
  { time: 'Day 17 • 21:30', title: 'Long Rest at Frostpine', detail: 'Recovered after the Icefang fight.' },
];

export const previewJournalDetail: RpgJournalDetailPreview = {
  title: 'Arrived at Glimmerdeep Pass',
  detail: 'The party makes its way through the winding mountain trail and reaches the ancient pass.',
  bullets: ['Discovered location: Glimmerdeep Pass', 'Weather: Cold, Windy', 'Detected tracks near the northern archway'],
  tags: ['Exploration', 'Discovery', 'Travel'],
};

export const inventoryItems: RpgInventoryItemPreview[] = [
  { icon: '🧪', count: '12', label: 'Healing potion' },
  { icon: '💧', count: '7', label: 'Mana tonic' },
  { icon: '🥩', count: '5', label: 'Trail rations' },
  { icon: '🔮', count: '3', label: 'Focus crystal' },
  { icon: '🪢', count: '2', label: 'Rope coil' },
  { icon: '🔥', count: '9', label: 'Torch' },
  { icon: '🍃', count: '4', label: 'Keenleaf' },
  { icon: '📜', count: '6', label: 'Scroll' },
];

export const hotbarAbilities: RpgHotbarAbilityPreview[] = [
  { key: '1', icon: '✦', label: 'Aimed Shot' },
  { key: '2', icon: '↯', label: 'Frost Arrow' },
  { key: '3', icon: '☘', label: 'Camouflage' },
  { key: '4', icon: '✹', label: 'Radiant Flare' },
  { key: '5', icon: '⟡', label: 'Volley' },
  { key: '6', icon: '⇥', label: 'Dash' },
];

export const previewWorldStateRows: RpgWorldStateRowPreview[] = [
  { icon: '☀', label: 'Time', value: 'Day 18 • 09:42' },
  { icon: '≋', label: 'Weather', value: 'Cold, Windy' },
  { icon: '❄', label: 'Temperature', value: '-12°C' },
  { icon: '✦', label: 'Reputation', value: 'Honored (35)' },
];

export const npcRelationships: RpgNpcRelationshipPreview[] = [
  { name: 'Thorin Ironfist', stance: 'Ally', score: 78 },
  { name: 'Elandra', stance: 'Ally', score: 64 },
  { name: 'Kael', stance: 'Ally', score: 52 },
  { name: 'Captain Bryn', stance: 'Neutral', score: 10 },
];

export const previewJobs: RpgJobCardPreview[] = [
  { id: 'preview-turn', title: 'rpg.turn', status: 'Running', progress: 68, detail: 'Load / Apply turn / Narrate / Checkpoint', source: 'preview' },
  { id: 'preview-narration', title: 'narration.generate', status: 'Running', progress: 42, detail: 'Generating presentation text', source: 'preview' },
  { id: 'preview-world', title: 'world.state.update', status: 'Queued', progress: 0, detail: 'Waiting for turn output', source: 'preview' },
];

export const previewSessionSummary: RpgSessionSummaryPreview = {
  id: 'preview-session',
  title: 'Preview campaign',
  location: 'Glimmerdeep Pass',
  summary:
    'The mountain winds howl through the narrow pass, carrying the scent of pine and snow. Jagged cliffs rise on both sides, and an ancient stone archway stands ahead, half-buried in drifts.',
  updatedAt: 'Day 18 • 09:42',
  turnLabel: 'Turn 18',
  checkpointLabel: 'Preview checkpoint',
  sortRank: 0,
  source: 'preview',
};

export function createRpgWorkspaceState(sources: RpgWorkspaceStateSources): RpgWorkspaceState {
  const sessions = sources.inventory?.sessions ?? [];
  const sessionSummaries = sessions
    .map(toSessionSummary)
    .sort((left, right) => right.sortRank - left.sortRank || left.title.localeCompare(right.title));
  const selectedSessionSummary =
    sessionSummaries.find((session) => session.id === sources.selectedSessionId) ?? sessionSummaries[0] ?? previewSessionSummary;
  const rpgJobs = sources.jobs?.jobs.filter((job) => job.module === 'rpg') ?? [];
  const rpgAssets = sources.assets?.assets.filter((asset) => asset.type === 'rpg_checkpoint' || asset.module === 'rpg') ?? [];
  const rpgReports = sources.reports?.reports?.filter((report) => report.kind.includes('rpg') || report.id.includes('rpg')) ?? [];
  const jobCards = rpgJobs.length ? rpgJobs.map(toJobCard) : previewJobs;
  const recentEvents = buildRecentEvents(selectedSessionSummary);
  const journalEntries = buildJournalEntries(selectedSessionSummary);
  const journalDetail = buildJournalDetail(selectedSessionSummary);
  const worldStateRows = buildWorldStateRows(selectedSessionSummary);
  const checkpointSummary = buildCheckpointSummary(rpgAssets, selectedSessionSummary);

  return {
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
    sessionSummaries,
    selectedSessionSummary,
    checkpointSummary,
    sessions,
    rpgJobs,
    rpgAssets,
    rpgReports,
    jobCards,
  };
}

export function safeSessionId(session: Record<string, unknown>, index: number): string {
  const candidate = session.session_id ?? session.id ?? session.name ?? `session:${index + 1}`;
  return String(candidate);
}

export function progressPercent(progress: { current: number; total: number } | undefined): number {
  if (!progress || progress.total <= 0) {
    return 0;
  }

  return Math.min(100, Math.round((progress.current / progress.total) * 100));
}

function toSessionSummary(session: RpgSession, index: number): RpgSessionSummaryPreview {
  const metadata = recordValue(session.metadata);
  const state = recordValue(session.state);
  const payload = recordValue(session.payload);
  const id = safeSessionId(session, index);
  const updatedRaw = firstString(session.updated_at, session.updatedAt, session.modified_at, session.created_at, metadata?.updated_at);
  const turnCount = firstNumber(session.turn_count, session.turns, session.current_turn, metadata?.turn_count, state?.turn_count);
  const checkpointLabel = firstString(session.checkpoint_id, session.checkpoint, session.checkpoint_path, session.storage_path, payload?.checkpoint_id) ?? 'Checkpoint indexed';

  return {
    id,
    title: firstString(session.title, session.name, session.label, session.session_id, session.id) ?? id,
    location:
      firstString(session.location, session.current_location, session.currentLocation, metadata?.location, metadata?.current_location, state?.location, payload?.location) ??
      previewSessionSummary.location,
    summary:
      firstString(session.summary, session.description, session.last_event, metadata?.summary, metadata?.last_event, state?.summary, payload?.summary) ??
      'Live replay-persistence session indexed by the backend.',
    updatedAt: compactTimestamp(updatedRaw) ?? 'Updated time unknown',
    turnLabel: typeof turnCount === 'number' ? `Turn ${turnCount}` : 'Turn count unknown',
    checkpointLabel,
    sortRank: timestampRank(updatedRaw),
    source: 'live',
  };
}

function buildRecentEvents(selectedSession: RpgSessionSummaryPreview): string[] {
  if (selectedSession.source === 'preview') {
    return previewRecentEvents;
  }

  return [
    `Loaded ${selectedSession.title}.`,
    `Current location: ${selectedSession.location}.`,
    `${selectedSession.turnLabel} • ${selectedSession.updatedAt}.`,
  ];
}

function buildJournalEntries(selectedSession: RpgSessionSummaryPreview): RpgJournalEntryPreview[] {
  if (selectedSession.source === 'preview') {
    return previewJournalEntries;
  }

  return [
    {
      time: selectedSession.updatedAt,
      title: `Selected ${selectedSession.title}`,
      detail: selectedSession.summary,
    },
    {
      time: selectedSession.turnLabel,
      title: 'Latest deterministic checkpoint',
      detail: selectedSession.checkpointLabel,
    },
    {
      time: 'Replay',
      title: 'Session ready',
      detail: 'Replay-preserving turn commands will continue from this indexed state.',
    },
  ];
}

function buildJournalDetail(selectedSession: RpgSessionSummaryPreview): RpgJournalDetailPreview {
  if (selectedSession.source === 'preview') {
    return previewJournalDetail;
  }

  return {
    title: `Live session: ${selectedSession.title}`,
    detail: selectedSession.summary,
    bullets: [
      `Session id: ${selectedSession.id}`,
      `Location: ${selectedSession.location}`,
      `${selectedSession.turnLabel} • ${selectedSession.updatedAt}`,
      `Checkpoint: ${selectedSession.checkpointLabel}`,
    ],
    tags: ['Live session', 'Replay-safe', 'Indexed'],
  };
}

function buildWorldStateRows(selectedSession: RpgSessionSummaryPreview): RpgWorldStateRowPreview[] {
  if (selectedSession.source === 'preview') {
    return previewWorldStateRows;
  }

  return [
    { icon: '☀', label: 'Updated', value: selectedSession.updatedAt },
    { icon: '⌁', label: 'Session', value: selectedSession.title },
    { icon: '◆', label: 'Turn', value: selectedSession.turnLabel },
    { icon: '▣', label: 'Mode', value: 'Replay-preserving' },
  ];
}

function buildCheckpointSummary(assets: RpgAsset[], selectedSession: RpgSessionSummaryPreview): RpgCheckpointSummaryPreview {
  if (!assets.length) {
    return {
      label: selectedSession.source === 'live' ? selectedSession.checkpointLabel : 'Preview only',
      detail: selectedSession.source === 'live' ? `Session checkpoint: ${selectedSession.id}` : 'No RPG checkpoint assets indexed',
      source: selectedSession.source,
    };
  }

  const latestAsset = [...assets].sort((left, right) => timestampRank(right.created_at) - timestampRank(left.created_at))[0];

  return {
    label: 'Latest checkpoint',
    detail: String(latestAsset.storage_path ?? latestAsset.id),
    source: 'live',
  };
}

function toJobCard(job: RpgJob): RpgJobCardPreview {
  return {
    id: String(job.id),
    title: String(job.type),
    status: String(job.status),
    progress: progressPercent(job.progress),
    detail: job.stages?.map((stage) => stage.label).join(' / ') || String(job.resource_class),
    source: 'live',
  };
}

function firstString(...values: unknown[]): string | undefined {
  for (const value of values) {
    if (typeof value === 'string' && value.trim()) {
      return value;
    }
  }

  return undefined;
}

function firstNumber(...values: unknown[]): number | undefined {
  for (const value of values) {
    if (typeof value === 'number' && Number.isFinite(value)) {
      return value;
    }

    if (typeof value === 'string' && value.trim()) {
      const parsed = Number(value);
      if (Number.isFinite(parsed)) {
        return parsed;
      }
    }
  }

  return undefined;
}

function recordValue(value: unknown): Record<string, unknown> | undefined {
  if (typeof value === 'object' && value !== null && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }

  return undefined;
}

function compactTimestamp(value: string | undefined): string | undefined {
  if (!value) {
    return undefined;
  }

  if (!value.includes('T')) {
    return value;
  }

  const [date, time = ''] = value.split('T');
  const [hour = '00', minute = '00'] = time.split(':');

  return `${date} ${hour}:${minute} UTC`;
}

function timestampRank(value: string | undefined): number {
  if (!value) {
    return 0;
  }

  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : 0;
}
