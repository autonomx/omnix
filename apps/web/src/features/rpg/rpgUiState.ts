import type { AssetListResponse, JobListResponse, PersistenceInventory, ReportListResponse } from '../../api/client';

export interface RpgHeroSummaryPreview {
  avatar: string;
  name: string;
  subtitle: string;
  origin: string;
  xpLabel: string;
  xpPercent: number;
  gold: string;
  renown: string;
  source: 'live' | 'preview';
}

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

export interface RpgEncounterPreview {
  icon: string;
  title: string;
  detail: string;
  source: 'live' | 'preview';
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
  heroSummary: RpgHeroSummaryPreview;
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
  encounter: RpgEncounterPreview;
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

export const previewHeroSummary: RpgHeroSummaryPreview = {
  avatar: 'A',
  name: 'Alyndra',
  subtitle: 'Level 14 • Ranger',
  origin: 'Wanderer of the North',
  xpLabel: '7,450 / 12,000',
  xpPercent: 62,
  gold: '1,248',
  renown: 'Honored (35)',
  source: 'preview',
};

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

export const previewEncounter: RpgEncounterPreview = {
  icon: '⚔',
  title: 'No active combat',
  detail: 'All quiet for now.',
  source: 'preview',
};

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
  turnLabel: 'Turn 12',
  checkpointLabel: 'Saved 2m ago',
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
  const selectedSession = selectedSessionSummary.source === 'live' ? findSessionById(sessions, selectedSessionSummary.id) : undefined;
  const rpgJobs = sources.jobs?.jobs.filter((job) => job.module === 'rpg') ?? [];
  const rpgAssets = sources.assets?.assets.filter((asset) => asset.type === 'rpg_checkpoint' || asset.module === 'rpg') ?? [];
  const rpgReports = sources.reports?.reports?.filter((report) => report.kind.includes('rpg') || report.id.includes('rpg')) ?? [];
  const jobCards = rpgJobs.length ? rpgJobs.map(toJobCard) : previewJobs;
  const recentEvents = buildRecentEvents(selectedSessionSummary);
  const journalEntries = buildJournalEntries(selectedSessionSummary);
  const journalDetail = buildJournalDetail(selectedSessionSummary);
  const worldStateRows = buildWorldStateRows(selectedSessionSummary, selectedSession);
  const checkpointSummary = buildCheckpointSummary(rpgAssets, selectedSessionSummary);

  return {
    heroSummary: buildHeroSummary(selectedSession),
    heroStats: buildHeroStats(selectedSession),
    equippedGear: buildEquippedGear(selectedSession),
    partyMembers: buildPartyMembers(selectedSession),
    activeQuests: buildActiveQuests(selectedSession),
    quickActions,
    recentEvents,
    journalEntries,
    journalDetail,
    inventoryItems: buildInventoryItems(selectedSession),
    hotbarAbilities,
    worldStateRows,
    npcRelationships: buildNpcRelationships(selectedSession),
    encounter: buildEncounter(selectedSession),
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

function findSessionById(sessions: RpgSession[], id: string): RpgSession | undefined {
  return sessions.find((session, index) => safeSessionId(session, index) === id);
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

function buildHeroSummary(session: RpgSession | undefined): RpgHeroSummaryPreview {
  const player = getPlayerRecord(session);
  if (!player) {
    return previewHeroSummary;
  }

  const stats = recordValue(player.stats);
  const resources = recordValue(player.resources);
  const reputation = recordValue(player.reputation);
  const name = firstString(player.name, player.character_name, player.characterName, player.hero_name, player.id) ?? previewHeroSummary.name;
  const level = firstNumber(player.level, stats?.level);
  const role = firstString(player.class, player.role, player.archetype, player.job) ?? 'Adventurer';
  const origin = firstString(player.background, player.origin, player.title, player.description) ?? 'Live RPG character';
  const xpMetric = readMetric([player, stats, resources], ['xp', 'experience'], ['xp_max', 'max_xp', 'xp_to_next', 'next_level_xp', 'experience_max']);
  const xpCurrent = firstNumber(player.xp, player.experience, stats?.xp, resources?.xp);
  const xpLabel = xpMetric ? metricLabel(xpMetric.current, xpMetric.max) : xpCurrent !== undefined ? formatNumber(xpCurrent) : previewHeroSummary.xpLabel;
  const xpPercent = xpMetric ? metricPercent(xpMetric.current, xpMetric.max) : previewHeroSummary.xpPercent;
  const gold = formatCurrency(player.currency, player.gold, player.money, resources?.gold, resources?.currency);
  const renown =
    firstString(player.renown, player.reputation, player.reputation_label, reputation?.label, reputation?.standing, reputation?.name) ??
    (firstNumber(player.renown, player.reputation_score, reputation?.score) !== undefined
      ? `Renown ${formatNumber(firstNumber(player.renown, player.reputation_score, reputation?.score) ?? 0)}`
      : previewHeroSummary.renown);

  return {
    avatar: initialFor(name),
    name,
    subtitle: [level !== undefined ? `Level ${level}` : undefined, role].filter(Boolean).join(' • '),
    origin,
    xpLabel,
    xpPercent,
    gold,
    renown,
    source: 'live',
  };
}

function buildHeroStats(session: RpgSession | undefined): RpgStatPreview[] {
  const player = getPlayerRecord(session);
  if (!player) {
    return heroStats;
  }

  const stats = recordValue(player.stats);
  const resources = recordValue(player.resources);
  const sources = [player, stats, resources];
  const hp = readMetric(sources, ['hp', 'health', 'hit_points'], ['max_hp', 'max_health', 'health_max', 'hp_max', 'max_hit_points']);
  const stamina = readMetric(sources, ['stamina', 'energy'], ['max_stamina', 'stamina_max', 'max_energy', 'energy_max']);
  const mana = readMetric(sources, ['mana', 'mp'], ['max_mana', 'mana_max', 'max_mp', 'mp_max']);

  return [
    hp ? toStat('HP', hp, 'danger') : heroStats[0],
    stamina ? toStat('Stamina', stamina, 'success') : heroStats[1],
    mana ? toStat('Mana', mana, 'mana') : heroStats[2],
  ];
}

function buildEquippedGear(session: RpgSession | undefined): RpgGearPreview[] {
  const player = getPlayerRecord(session);
  const equipment = firstArray(player?.equipment, player?.equipped, player?.gear, recordValue(player?.inventory)?.equipped);
  if (!equipment.length) {
    return equippedGear;
  }

  return equipment.slice(0, 5).map((item, index) => {
    const record = recordValue(item) ?? { name: item };
    const slot = firstString(record.slot, record.type, record.category) ?? `Slot ${index + 1}`;
    const name = firstString(record.name, record.label, record.id) ?? `Equipped item ${index + 1}`;
    return { icon: iconForEquipment(slot, name), name, slot: titleCase(slot) };
  });
}

function buildPartyMembers(session: RpgSession | undefined): RpgPartyMemberPreview[] {
  const roots = getSessionRecords(session);
  const party = firstArray(...roots.flatMap((root) => [root.party, root.companions, root.party_members]));
  if (!party.length) {
    return partyMembers;
  }

  return party.slice(0, 4).map((member, index) => {
    const record = recordValue(member) ?? { name: member };
    const name = firstString(record.name, record.id, record.label) ?? `Companion ${index + 1}`;
    const level = firstNumber(record.level, record.lv);
    const role = firstString(record.role, record.class, record.archetype, record.type) ?? 'Companion';
    const hp = readMetric([record, recordValue(record.stats), recordValue(record.resources)], ['hp', 'health'], ['max_hp', 'max_health', 'health_max']);
    return {
      avatar: initialFor(name),
      name,
      role: [level !== undefined ? `Lv. ${level}` : undefined, role].filter(Boolean).join(' '),
      hp: hp ? metricLabel(hp.current, hp.max) : 'HP unknown',
      percent: hp ? metricPercent(hp.current, hp.max) : 50,
    };
  });
}

function buildActiveQuests(session: RpgSession | undefined): RpgQuestPreview[] {
  const roots = getSessionRecords(session);
  const quests = firstArray(...roots.flatMap((root) => [root.quests, root.active_quests, root.objectives, recordValue(root.journal)?.quests]));
  if (!quests.length) {
    return activeQuests;
  }

  return quests.slice(0, 4).map((quest, index) => {
    const record = recordValue(quest) ?? { title: quest };
    const title = firstString(record.title, record.name, record.id) ?? `Quest ${index + 1}`;
    const detail = firstString(record.detail, record.description, record.objective, record.next_step, record.summary) ?? 'Objective indexed in live session state.';
    return { icon: questIcon(record.status), title, detail };
  });
}

function buildInventoryItems(session: RpgSession | undefined): RpgInventoryItemPreview[] {
  const player = getPlayerRecord(session);
  const roots = getSessionRecords(session);
  const inventory = firstArray(player?.inventory, recordValue(player?.inventory)?.items, ...roots.map((root) => recordValue(root.inventory)?.items ?? root.items));
  if (!inventory.length) {
    return inventoryItems;
  }

  return inventory.slice(0, 8).map((item, index) => {
    const record = recordValue(item) ?? { name: item };
    const label = firstString(record.name, record.label, record.id) ?? `Item ${index + 1}`;
    const count = firstNumber(record.count, record.quantity, record.qty, record.amount);
    return { icon: iconForInventory(label), count: count !== undefined ? formatNumber(count) : '1', label };
  });
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

function buildWorldStateRows(selectedSession: RpgSessionSummaryPreview, session: RpgSession | undefined): RpgWorldStateRowPreview[] {
  if (selectedSession.source === 'preview' || !session) {
    return previewWorldStateRows;
  }

  const roots = getSessionRecords(session);
  const world = firstRecord(
    ...roots.flatMap((root) => [root.world, root.world_state, root.environment, root.location_state, root.locationContext, recordValue(root.state)?.world])
  );
  const clock = firstRecord(...roots.flatMap((root) => [root.clock, root.time, root.calendar, world?.clock, world?.time]));
  const player = getPlayerRecord(session);
  const reputation = recordValue(player?.reputation);
  const time = firstString(
    world?.time,
    world?.time_label,
    world?.day_time,
    clock?.label,
    clock?.time,
    clock?.day,
    ...roots.map((root) => root.time_label ?? root.time)
  ) ?? selectedSession.updatedAt;
  const weather = firstString(world?.weather, world?.conditions, world?.weather_label, ...roots.map((root) => root.weather ?? root.conditions));
  const temperatureNumber = firstNumber(world?.temperature, world?.temp, ...roots.map((root) => root.temperature ?? root.temp));
  const temperature = firstString(world?.temperature_label, world?.temperature, world?.temp, ...roots.map((root) => root.temperature_label)) ??
    (temperatureNumber !== undefined ? `${formatNumber(temperatureNumber)}°C` : undefined);
  const reputationLabel =
    firstString(player?.renown, player?.reputation_label, reputation?.label, reputation?.standing, reputation?.name) ??
    (firstNumber(player?.renown, player?.reputation_score, reputation?.score) !== undefined
      ? `Renown ${formatNumber(firstNumber(player?.renown, player?.reputation_score, reputation?.score) ?? 0)}`
      : undefined);

  return [
    { icon: '☀', label: 'Time', value: time },
    { icon: '≋', label: 'Weather', value: weather ?? 'Weather unknown' },
    { icon: '❄', label: 'Temperature', value: temperature ?? 'Unknown' },
    { icon: '✦', label: 'Reputation', value: reputationLabel ?? 'Reputation unknown' },
  ];
}

function buildNpcRelationships(session: RpgSession | undefined): RpgNpcRelationshipPreview[] {
  const roots = getSessionRecords(session);
  const candidates = roots.flatMap((root) => [
    root.npc_relationships,
    root.relationships,
    root.social_state,
    root.social,
    recordValue(root.npcs)?.relationships,
    recordValue(root.memory)?.npc_relationships,
  ]);
  const relationshipArray = firstArray(...candidates);
  const relationshipRecord = relationshipArray.length ? undefined : firstRecord(...candidates);
  const relationshipItems = relationshipArray.length
    ? relationshipArray
    : relationshipRecord
      ? Object.entries(relationshipRecord).map(([name, value]) => ({ ...(recordValue(value) ?? { score: value }), name }))
      : [];

  if (!relationshipItems.length) {
    return npcRelationships;
  }

  return relationshipItems.slice(0, 5).map((relationship, index) => {
    const record = recordValue(relationship) ?? { name: relationship };
    const name = firstString(record.name, record.npc, record.character, record.id, record.label) ?? `NPC ${index + 1}`;
    const score = relationshipScore(firstNumber(record.score, record.affinity, record.trust, record.value, record.relationship, record.standing_score));
    const stance = firstString(record.stance, record.status, record.relationship_label, record.label) ?? stanceForScore(score);
    return { name, stance, score };
  });
}

function buildEncounter(session: RpgSession | undefined): RpgEncounterPreview {
  const roots = getSessionRecords(session);
  const encounter = firstRecord(
    ...roots.flatMap((root) => [root.encounter, root.encounter_state, root.current_encounter, root.combat, root.combat_state, recordValue(root.state)?.combat])
  );
  if (!encounter) {
    return previewEncounter;
  }

  const status = firstString(encounter.status, encounter.state, encounter.phase, encounter.mode);
  const enemies = firstArray(encounter.enemies, encounter.opponents, encounter.hostiles, encounter.combatants)
    .map((enemy, index) => firstString(recordValue(enemy)?.name, recordValue(enemy)?.id, enemy) ?? `Combatant ${index + 1}`)
    .slice(0, 3);
  const statusText = String(status ?? '').toLowerCase();
  const active = Boolean(status && !['none', 'idle', 'inactive', 'resolved', 'complete', 'completed'].some((token) => statusText.includes(token)));
  const title = firstString(encounter.title, encounter.name, encounter.label) ?? (active ? 'Active encounter' : 'Encounter indexed');
  const detail =
    firstString(encounter.summary, encounter.detail, encounter.description, encounter.objective) ??
    (enemies.length ? `Combatants: ${enemies.join(', ')}` : status ? `Status: ${status}` : 'Encounter state indexed from live session.');

  return {
    icon: active ? '⚔' : '◇',
    title,
    detail,
    source: 'live',
  };
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

function toStat(label: string, metric: { current: number; max: number }, tone: RpgStatPreview['tone']): RpgStatPreview {
  return { label, value: metricLabel(metric.current, metric.max), percent: metricPercent(metric.current, metric.max), tone };
}

function getPlayerRecord(session: RpgSession | undefined): Record<string, unknown> | undefined {
  if (!session) {
    return undefined;
  }

  const roots = getSessionRecords(session);
  return firstRecord(
    ...roots.flatMap((root) => [root.player, root.hero, root.character, root.player_state, root.character_state, recordValue(root.state)?.player])
  );
}

function getSessionRecords(session: RpgSession | undefined): Record<string, unknown>[] {
  if (!session) {
    return [];
  }

  const sessionRecord = session as Record<string, unknown>;
  return [sessionRecord, recordValue(sessionRecord.metadata), recordValue(sessionRecord.state), recordValue(sessionRecord.payload)].filter(
    (record): record is Record<string, unknown> => Boolean(record)
  );
}

function readMetric(
  records: Array<Record<string, unknown> | undefined>,
  currentKeys: string[],
  maxKeys: string[]
): { current: number; max: number } | undefined {
  for (const record of records) {
    if (!record) {
      continue;
    }

    const nestedMetric = firstRecord(...currentKeys.map((key) => recordValue(record[key])));
    const nestedCurrent = firstNumber(nestedMetric?.current, nestedMetric?.value, nestedMetric?.amount);
    const nestedMax = firstNumber(nestedMetric?.max, nestedMetric?.total, nestedMetric?.maximum);
    if (nestedCurrent !== undefined && nestedMax !== undefined) {
      return { current: nestedCurrent, max: nestedMax };
    }

    const current = firstNumber(...currentKeys.flatMap((key) => [record[key], record[`current_${key}`], record[`current${titleCase(key)}`]]));
    const max = firstNumber(...maxKeys.flatMap((key) => [record[key], record[`maximum_${key}`]]));
    if (current !== undefined && max !== undefined) {
      return { current, max };
    }
  }

  return undefined;
}

function formatCurrency(...values: unknown[]): string {
  const currencyRecord = firstRecord(...values.map((value) => recordValue(value)));
  if (currencyRecord) {
    const gold = firstNumber(currencyRecord.gold, currencyRecord.gp, currencyRecord.coins);
    const silver = firstNumber(currencyRecord.silver, currencyRecord.sp);
    const copper = firstNumber(currencyRecord.copper, currencyRecord.cp);
    if (gold !== undefined || silver !== undefined || copper !== undefined) {
      return [gold !== undefined ? `${formatNumber(gold)}g` : undefined, silver !== undefined ? `${formatNumber(silver)}s` : undefined, copper !== undefined ? `${formatNumber(copper)}c` : undefined]
        .filter(Boolean)
        .join(' ');
    }
  }

  const numeric = firstNumber(...values);
  if (numeric !== undefined) {
    return formatNumber(numeric);
  }

  return firstString(...values) ?? previewHeroSummary.gold;
}

function metricLabel(current: number, max: number): string {
  return `${formatNumber(current)} / ${formatNumber(max)}`;
}

function metricPercent(current: number, max: number): number {
  if (max <= 0) {
    return 0;
  }

  return Math.max(0, Math.min(100, Math.round((current / max) * 100)));
}

function relationshipScore(value: number | undefined): number {
  if (value === undefined) {
    return 50;
  }

  if (value > 0 && value <= 1) {
    return Math.round(value * 100);
  }

  return Math.max(0, Math.min(100, Math.round(value)));
}

function stanceForScore(score: number): string {
  if (score >= 75) return 'Ally';
  if (score >= 55) return 'Friendly';
  if (score >= 35) return 'Neutral';
  if (score >= 15) return 'Wary';
  return 'Hostile';
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
      const parsed = Number(value.replace(/,/g, ''));
      if (Number.isFinite(parsed)) {
        return parsed;
      }
    }
  }

  return undefined;
}

function firstRecord(...values: unknown[]): Record<string, unknown> | undefined {
  return values.map(recordValue).find(Boolean);
}

function firstArray(...values: unknown[]): unknown[] {
  for (const value of values) {
    if (Array.isArray(value)) {
      return value;
    }
  }

  return [];
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

function formatNumber(value: number): string {
  return new Intl.NumberFormat('en-US').format(value);
}

function initialFor(name: string): string {
  return name.trim().charAt(0).toUpperCase() || 'A';
}

function titleCase(value: string): string {
  return value
    .replace(/[_-]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function iconForEquipment(slot: string, name: string): string {
  const text = `${slot} ${name}`.toLowerCase();
  if (text.includes('bow')) return '🏹';
  if (text.includes('armor') || text.includes('shield')) return '🛡️';
  if (text.includes('ring')) return '💍';
  if (text.includes('cloak')) return '🦉';
  if (text.includes('sword') || text.includes('blade')) return '⚔';
  return '◇';
}

function iconForInventory(label: string): string {
  const text = label.toLowerCase();
  if (text.includes('potion') || text.includes('heal')) return '🧪';
  if (text.includes('mana')) return '💧';
  if (text.includes('ration') || text.includes('food')) return '🥩';
  if (text.includes('rope')) return '🪢';
  if (text.includes('torch') || text.includes('fire')) return '🔥';
  if (text.includes('scroll') || text.includes('letter')) return '📜';
  return '▣';
}

function questIcon(status: unknown): string {
  const text = String(status ?? '').toLowerCase();
  if (text.includes('complete')) return '✓';
  if (text.includes('failed')) return '×';
  if (text.includes('urgent')) return '▲';
  return '◆';
}
