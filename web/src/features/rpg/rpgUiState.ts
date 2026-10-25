import type { AssetListResponse, JobListResponse, ReportListResponse } from '../../api/client';
import { jobProgressPercent } from '../../api/jobProgress';
import { buildInteractionStoryMessages, buildJournalDetail, buildJournalEntries, buildRecentEvents, buildRpgTurnJobTimelineEvents, buildStoryMessages, buildTimelineEvents } from './rpgStoryState';
import { NOT_TRACKED, activeQuests, equippedGear, heroStats, hotbarAbilities, inventoryItems, npcRelationships, partyMembers, previewHeroSummary, previewJobs, previewSessionSummary, previewSurvival, previewWorldStateRows, quickActions } from './rpgUiPreview';
import { compactTimestamp, emptyHeroStats, emptyStat, firstArray, firstNumber, firstRecord, firstString, formatCurrency, formatNumber, getEnvironmentSnapshot, getPlayerRecord, getSessionRecords, iconForEquipment, iconForInventory, initialFor, metricLabel, metricPercent, questIcon, quickActionIcon, quickActionLabel, readMetric, recordValue, relationshipScore, stanceForScore, timestampRank, titleCase, toStat } from './rpgUiRecords';
import type { RpgAsset, RpgCheckpointSummaryPreview, RpgGearPreview, RpgHeroSummaryPreview, RpgHotbarAbilityPreview, RpgInventoryItemPreview, RpgJob, RpgJobCardPreview, RpgJournalDetailPreview, RpgJournalEntryPreview, RpgNpcRelationshipPreview, RpgPartyMemberPreview, RpgQuestPreview, RpgQuickActionPreview, RpgReport, RpgSession, RpgSessionSummaryPreview, RpgStatPreview, RpgStoryMessagePreview, RpgSurvivalNeedPreview, RpgSurvivalPreview, RpgWorldStateRowPreview } from './rpgUiTypes';

export interface RpgWorkspaceState {
  heroSummary: RpgHeroSummaryPreview;
  heroStats: RpgStatPreview[];
  survival: RpgSurvivalPreview;
  equippedGear: RpgGearPreview[];
  partyMembers: RpgPartyMemberPreview[];
  activeQuests: RpgQuestPreview[];
  quickActions: RpgQuickActionPreview[];
  storyMessages: RpgStoryMessagePreview[];
  recentEvents: string[];
  journalEntries: RpgJournalEntryPreview[];
  narrativeLogEntries: RpgJournalEntryPreview[];
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
  inventory?: { sessions?: RpgSession[] };
  jobs?: JobListResponse;
  assets?: AssetListResponse;
  reports?: ReportListResponse;
  selectedSessionId?: string;
  selectedSession?: RpgSession;
}

export function createRpgWorkspaceState(sources: RpgWorkspaceStateSources): RpgWorkspaceState {
  const sessions = sources.inventory?.sessions ?? [];
  const sessionSummaries = sessions
    .map(toSessionSummary)
    .sort((left, right) => right.sortRank - left.sortRank || left.title.localeCompare(right.title));
  const requestedSessionId = sources.selectedSessionId?.trim();
  const selectedInventorySummary = requestedSessionId
    ? sessionSummaries.find((session) => session.id === requestedSessionId)
    : undefined;
  const selectedResponseSession = requestedSessionId && sessionMatchesId(sources.selectedSession, requestedSessionId)
    ? sources.selectedSession
    : undefined;
  const selectedSessionSummary =
    selectedInventorySummary
    ?? (selectedResponseSession ? toSessionSummary(selectedResponseSession, 0) : undefined)
    ?? (requestedSessionId ? pendingSessionSummary(requestedSessionId) : sessionSummaries[0])
    ?? previewSessionSummary;
  const selectedSession =
    selectedSessionSummary.source === 'live'
      ? selectedResponseSession ?? findSessionById(sessions, selectedSessionSummary.id)
      : undefined;
  const rpgJobs = sources.jobs?.jobs?.filter((job) => job.module === 'rpg') ?? [];
  const rpgAssets = sources.assets?.assets?.filter((asset) => asset.type === 'rpg_checkpoint' || asset.module === 'rpg') ?? [];
  const rpgReports = sources.reports?.reports?.filter((report) => report.kind.includes('rpg') || report.id.includes('rpg')) ?? [];
  const jobCards = rpgJobs.length
    ? [...rpgJobs].sort(compareRpgJobsForCards).map(toJobCard)
    : selectedSessionSummary.source === 'live' ? [] : previewJobs;
  const heroSummary = buildHeroSummary(selectedSession);
  const persistedStoryMessages = buildInteractionStoryMessages(selectedSession, heroSummary);
  const turnMessages = buildRpgTurnJobTimelineEvents(rpgJobs, selectedSessionSummary.id, heroSummary.name);
  const sessionTimeline = buildTimelineEvents(selectedSession);
  const timeline = [
    ...turnMessages,
    ...sessionTimeline,
  ].slice(0, 12);
  const storyMessages = persistedStoryMessages.length
    ? persistedStoryMessages
    : buildStoryMessages(turnMessages, heroSummary);
  const recentEvents = buildRecentEvents(selectedSessionSummary, sessionTimeline);
  const narrativeLogEntries = timeline.map((event) => ({ time: event.time, title: event.title, detail: event.detail }));
  const journalEntries = buildJournalEntries(selectedSessionSummary, selectedSession);
  const journalDetail = buildJournalDetail(selectedSessionSummary, journalEntries);
  const worldStateRows = buildWorldStateRows(selectedSessionSummary, selectedSession);
  const checkpointSummary = buildCheckpointSummary(rpgAssets, selectedSessionSummary);

  return {
    heroSummary,
    heroStats: buildHeroStats(selectedSession),
    survival: buildSurvivalState(selectedSession),
    equippedGear: buildEquippedGear(selectedSession),
    partyMembers: buildPartyMembers(selectedSession),
    activeQuests: buildActiveQuests(selectedSession),
    quickActions: buildQuickActions(selectedSession),
    storyMessages,
    recentEvents,
    journalEntries,
    narrativeLogEntries,
    journalDetail,
    inventoryItems: buildInventoryItems(selectedSession),
    hotbarAbilities: buildHotbarAbilities(selectedSession),
    worldStateRows,
    npcRelationships: buildNpcRelationships(selectedSession),
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
  const manifest = recordValue(session.manifest);
  const candidate = session.session_id ?? session.id ?? manifest?.session_id ?? manifest?.id ?? session.name ?? `session:${index + 1}`;
  return String(candidate);
}

export const progressPercent = jobProgressPercent;

function findSessionById(sessions: RpgSession[], id: string): RpgSession | undefined {
  return sessions.find((session, index) => safeSessionId(session, index) === id);
}

function pendingSessionSummary(id: string): RpgSessionSummaryPreview {
  return {
    id,
    title: 'Loading selected campaign',
    location: 'Loading location',
    summary: 'Loading the selected campaign without displaying another session.',
    updatedAt: 'Refreshing session',
    turnLabel: 'Turn count pending',
    checkpointLabel: 'Checkpoint pending',
    sortRank: Number.MAX_SAFE_INTEGER,
    source: 'live',
  };
}

function sessionMatchesId(session: RpgSession | undefined, id: string): boolean {
  if (!session) return false;
  const manifest = recordValue(session.manifest);
  const sessionId = firstString(session.session_id, session.id, manifest?.session_id, manifest?.id);
  return sessionId === id;
}

function toSessionSummary(session: RpgSession, index: number): RpgSessionSummaryPreview {
  const manifest = recordValue(session.manifest);
  const metadata = recordValue(session.metadata);
  const state = recordValue(session.state);
  const publishedWorld = recordValue(state?.published_world);
  const payload = recordValue(session.payload);
  const latestTimeline = buildTimelineEvents(session)[0];
  const snapshot = getEnvironmentSnapshot(session);
  const context = recordValue(snapshot?.context);
  const id = safeSessionId(session, index);
  const updatedRaw = firstString(
    session.updated_at,
    session.updatedAt,
    session.modified_at,
    session.created_at,
    manifest?.updated_at,
    manifest?.created_at,
    metadata?.updated_at,
    latestTimeline?.time,
  );
  const turnCount = firstNumber(session.turn_count, session.turns, session.current_turn, manifest?.turn_count, metadata?.turn_count, state?.turn_count);
  const checkpointLabel = firstString(session.checkpoint_id, session.checkpoint, session.checkpoint_path, session.storage_path, payload?.checkpoint_id) ?? 'Checkpoint indexed';
  const title = firstString(session.title, session.name, session.label, manifest?.title, session.session_id, session.id, manifest?.session_id, manifest?.id) ?? id;
  const location = firstString(
    context?.location_label,
    session.location,
    session.current_location,
    session.currentLocation,
    metadata?.location,
    metadata?.current_location,
    state?.location,
    payload?.location
  ) ?? NOT_TRACKED;
  // The place as the scene describes it now (the sheet's summary is the opening's); nothing rather than filler.
  const summary =
    firstString(recordValue(recordValue(session.runtime_state)?.current_scene)?.summary, latestTimeline?.detail, session.summary,
      session.description, session.last_event, metadata?.summary, metadata?.last_event, state?.summary, payload?.summary) ?? '';

  return {
    id,
    worldId: firstString(
      session.world_id,
      metadata?.world_id,
      state?.world_id,
      publishedWorld?.world_id,
      payload?.world_id,
    ),
    title,
    location,
    summary,
    updatedAt: compactTimestamp(updatedRaw) ?? 'Updated time unknown',
    turnLabel: typeof turnCount === 'number' && turnCount > 0 ? `Turn ${turnCount}` : latestTimeline?.time !== undefined ? latestTimeline.time : 'No turns yet',
    checkpointLabel,
    sortRank: timestampRank(updatedRaw),
    lastPlayedMs: timestampRank(updatedRaw) || undefined,
    source: 'live',
  };
}

function buildHeroSummary(session: RpgSession | undefined): RpgHeroSummaryPreview {
  const player = getPlayerRecord(session);
  if (!player) {
    if (!session) return previewHeroSummary;
    return {
      avatar: '?',
      name: 'Character data unavailable',
      subtitle: 'Live session',
      origin: 'Character details are not present in the loaded session.',
      xpLabel: NOT_TRACKED,
      xpPercent: 0,
      gold: NOT_TRACKED,
      source: 'live',
    };
  }
  const stats = recordValue(player.stats);
  const resources = recordValue(player.resources);
  const name = firstString(player.name, player.character_name, player.characterName, player.hero_name, player.id) ?? 'Unnamed hero';
  const level = firstNumber(player.level, stats?.level);
  const role = firstString(player.class, player.role, player.archetype, player.job) ?? 'Adventurer';
  const origin = firstString(player.background, player.origin, player.title, player.description) ?? 'Live RPG character';
  const xpMetric = readMetric([player, stats, resources], ['xp', 'experience'], ['xp_max', 'max_xp', 'xp_to_next', 'next_level_xp', 'experience_max']);
  const xpCurrent = firstNumber(player.xp, player.experience, stats?.xp, resources?.xp);
  const xpLabel = xpMetric ? metricLabel(xpMetric.current, xpMetric.max) : xpCurrent !== undefined ? formatNumber(xpCurrent) : NOT_TRACKED;
  const xpPercent = xpMetric ? metricPercent(xpMetric.current, xpMetric.max) : 0;
  const gold = formatCurrency(player.currency, player.gold, player.money, resources?.gold, resources?.currency);
  return { avatar: initialFor(name), name, subtitle: [level !== undefined ? `Level ${level}` : undefined, role].filter(Boolean).join(' • '), origin, xpLabel, xpPercent, gold, source: 'live' };
}

function buildHeroStats(session: RpgSession | undefined): RpgStatPreview[] {
  const player = getPlayerRecord(session);
  if (!player) return session ? emptyHeroStats() : heroStats;
  const stats = recordValue(player.stats);
  const resources = recordValue(player.resources);
  const sources = [player, stats, resources];
  const hp = readMetric(sources, ['hp', 'health', 'hit_points'], ['max_hp', 'max_health', 'health_max', 'hp_max', 'max_hit_points']);
  const stamina = readMetric(sources, ['stamina', 'energy'], ['max_stamina', 'stamina_max', 'max_energy', 'energy_max']);
  const mana = readMetric(sources, ['mana', 'mp'], ['max_mana', 'mana_max', 'max_mp', 'mp_max']);
  return [
    hp ? toStat('HP', hp, 'danger') : emptyStat('HP', 'danger'),
    stamina ? toStat('Stamina', stamina, 'success') : emptyStat('Stamina', 'success'),
    mana ? toStat('Mana', mana, 'mana') : emptyStat('Mana', 'mana'),
  ];
}

function buildSurvivalState(session: RpgSession | undefined): RpgSurvivalPreview {
  if (!session) return previewSurvival;

  const simulation = recordValue(session.simulation_state) ?? {};
  const climate = recordValue(simulation.climate_survival);
  const climateNeeds = recordValue(climate?.survival);
  const playerState = recordValue(simulation.player_state) ?? getPlayerRecord(session) ?? {};
  const playerNeeds = recordValue(playerState.survival_state);
  const resources = recordValue(playerState.resources);
  const legacyNeeds = recordValue(simulation.survival);
  const readNeed = (key: 'hunger' | 'thirst' | 'fatigue') => Math.max(
    0,
    Math.min(100, firstNumber(climateNeeds?.[key], playerNeeds?.[key], resources?.[key], legacyNeeds?.[key]) ?? 0),
  );
  const values = {
    hunger: readNeed('hunger'),
    thirst: readNeed('thirst'),
    fatigue: readNeed('fatigue'),
  };
  const warnings = firstArray(climateNeeds?.warnings, playerNeeds?.warnings, legacyNeeds?.warnings)
    .map((warning) => firstString(warning))
    .filter((warning): warning is string => Boolean(warning))
    .map((warning) => titleCase(warning));
  const maxPressure = Math.max(values.hunger, values.thirst, values.fatigue);
  const status: RpgSurvivalPreview['status'] = maxPressure >= 85
    ? 'Critical'
    : maxPressure >= 60 || warnings.length
      ? 'Warning'
      : 'Stable';
  const need = (id: RpgSurvivalNeedPreview['id'], label: string): RpgSurvivalNeedPreview => ({
    id,
    label,
    percent: values[id],
    severity: values[id] >= 85 ? 'critical' : values[id] >= 60 ? 'warning' : 'stable',
    value: `${values[id]} / 100`,
  });

  return {
    actions: [
      { label: 'Eat', icon: 'E', command: 'I eat rations' },
      { label: 'Drink', icon: 'D', command: 'I drink water' },
      { label: 'Rest', icon: 'R', command: 'I rest' },
    ],
    detail: status === 'Critical'
      ? 'Immediate survival relief is recommended.'
      : status === 'Warning'
        ? 'One or more needs are creating survival pressure.'
        : 'Hunger, thirst and fatigue rise as time passes; eat, drink and rest to ease them.',
    needs: [need('hunger', 'Hunger'), need('thirst', 'Thirst'), need('fatigue', 'Fatigue')],
    source: 'live',
    status,
    warnings,
  };
}

function buildEquippedGear(session: RpgSession | undefined): RpgGearPreview[] {
  if (!session) return equippedGear;
  const player = getPlayerRecord(session);
  const equipment = firstArray(player?.equipment, player?.equipped, player?.gear, recordValue(player?.inventory)?.equipped);
  if (!equipment.length) return [];
  return equipment.slice(0, 5).map((item, index) => {
    const record = recordValue(item) ?? { name: item };
    const slot = firstString(record.slot, record.type, record.category) ?? `Slot ${index + 1}`;
    const name = firstString(record.name, record.label, record.id) ?? `Equipped item ${index + 1}`;
    return { icon: iconForEquipment(slot, name), name, slot: titleCase(slot) };
  });
}

function buildPartyMembers(session: RpgSession | undefined): RpgPartyMemberPreview[] {
  if (!session) return partyMembers;
  const roots = getSessionRecords(session);
  const party = firstArray(...roots.flatMap((root) => [root.party, root.companions, root.party_members]));
  if (!party.length) return [];
  return party.slice(0, 4).map((member, index) => {
    const record = recordValue(member) ?? { name: member };
    const name = firstString(record.name, record.id, record.label) ?? `Companion ${index + 1}`;
    const level = firstNumber(record.level, record.lv);
    const role = firstString(record.role, record.class, record.archetype, record.type) ?? 'Companion';
    const hp = readMetric([record, recordValue(record.stats), recordValue(record.resources)], ['hp', 'health'], ['max_hp', 'max_health', 'health_max']);
    return { avatar: initialFor(name), name, role: [level !== undefined ? `Lv. ${level}` : undefined, role].filter(Boolean).join(' '), hp: hp ? metricLabel(hp.current, hp.max) : 'HP unknown', percent: hp ? metricPercent(hp.current, hp.max) : 50 };
  });
}

function buildActiveQuests(session: RpgSession | undefined): RpgQuestPreview[] {
  if (!session) return activeQuests;
  const roots = getSessionRecords(session);
  const quests = firstArray(...roots.flatMap((root) => [root.quests, root.active_quests, root.objectives, recordValue(root.journal)?.quests]));
  if (!quests.length) return [];
  return quests.slice(0, 4).map((quest, index) => {
    const record = recordValue(quest) ?? { title: quest };
    const title = firstString(record.title, record.name, record.id) ?? `Quest ${index + 1}`;
    const detail = firstString(record.detail, record.description, record.objective, record.next_step, record.summary) ?? 'Objective indexed in live session state.';
    return { icon: questIcon(record.status), title, detail };
  });
}

function buildInventoryItems(session: RpgSession | undefined): RpgInventoryItemPreview[] {
  if (!session) return inventoryItems;
  const player = getPlayerRecord(session);
  const roots = getSessionRecords(session);
  const inventoryState = recordValue(player?.inventory_state);
  const inventory = firstArray(
    // The sheet's pack first: each thing with what the rules let the hero do with it (the player view's).
    recordValue(recordValue(session.state)?.player)?.inventory,
    inventoryState?.items,
    player?.inventory_items,
    player?.inventory,
    recordValue(player?.inventory)?.items,
    ...roots.map((root) => recordValue(root.inventory)?.items ?? root.items),
  );
  if (!inventory.length) return [];
  return inventory.map((item, index) => {
    const record = recordValue(item) ?? { name: item };
    const label = firstString(record.name, record.label, record.id) ?? `Item ${index + 1}`;
    const count = firstNumber(record.count, record.quantity, record.qty, record.amount);
    return {
      icon: iconForInventory(label),
      count: count !== undefined ? formatNumber(count) : '1',
      label,
      actions: Array.isArray(record.actions) ? record.actions.filter((action): action is string => typeof action === 'string') : undefined,
      category: firstString(record.category, record.type),
      description: firstString(record.description),
      worn: typeof record.worn === 'boolean' ? record.worn : undefined,
    };
  });
}

function buildQuickActions(session: RpgSession | undefined): RpgQuickActionPreview[] {
  if (!session) return quickActions;
  const roots = getSessionRecords(session);
  const actions = firstArray(
    ...roots.flatMap((root) => [
      root.quick_actions,
      root.suggested_actions,
      recordValue(root.narrative_affordances)?.suggested_actions,
      recordValue(recordValue(root.last_turn_contract)?.presentation)?.available_actions,
    ]),
  );
  return actions.slice(0, 6).map((action, index) => {
    const record = recordValue(action);
    const command = firstString(record?.command, record?.action, record?.text, action) ?? `Review live action ${index + 1}`;
    const label = firstString(record?.label, record?.title, record?.name) ?? quickActionLabel(command);
    return { label, icon: quickActionIcon(command), command };
  });
}

function buildHotbarAbilities(session: RpgSession | undefined): RpgHotbarAbilityPreview[] {
  if (!session) return hotbarAbilities;
  const roots = getSessionRecords(session);
  const hotbar = firstRecord(...roots.flatMap((root) => [root.hotbar, recordValue(root.ability_state)?.hotbar]));
  const abilities = firstArray(...roots.map((root) => recordValue(root.ability_tree)?.abilities));
  const abilityById = new Map(
    abilities.map((ability) => {
      const record = recordValue(ability) ?? {};
      return [firstString(record.ability_id, record.id) ?? '', record] as const;
    }),
  );
  if (!hotbar) return [];
  return Object.entries(hotbar)
    .sort(([left], [right]) => Number(left) - Number(right))
    .slice(0, 6)
    .map(([slot, value]) => {
      const valueRecord = recordValue(value);
      const abilityId = firstString(valueRecord?.ability_id, valueRecord?.id, value);
      const ability = abilityId ? abilityById.get(abilityId) : undefined;
      return {
        key: slot,
        icon: firstString(ability?.icon, valueRecord?.icon) ?? '✦',
        label: firstString(ability?.name, valueRecord?.name, abilityId ? titleCase(abilityId) : undefined) ?? `Hotbar ${slot}`,
        abilityId,
        description: firstString(ability?.description, valueRecord?.description),
      };
    });
}

function buildWorldStateRows(selectedSession: RpgSessionSummaryPreview, session: RpgSession | undefined): RpgWorldStateRowPreview[] {
  if (selectedSession.source === 'preview' || !session) return previewWorldStateRows;
  const snapshot = getEnvironmentSnapshot(session);
  if (!snapshot) {
    return environmentRowsFromValues({});
  }
  const calendar = recordValue(snapshot.calendar);
  const weather = recordValue(snapshot.weather);
  const context = recordValue(snapshot.context);
  const display = recordValue(snapshot.display);
  const hazards = firstArray(snapshot.hazards);
  return environmentRowsFromValues({
    season: firstString(display?.season, calendar?.season_label, snapshot.season_label),
    dayTime: firstString(display?.day_time, calendar?.time_label, snapshot.time_label),
    region: firstString(display?.region, snapshot.region_id),
    weather: firstString(display?.weather, weather?.label, weather?.condition),
    temperature: firstString(display?.temperature, snapshot.temperature_label, snapshot.temperature_c),
    wind: firstString(display?.wind, snapshot.wind),
    visibility: firstString(display?.visibility, snapshot.visibility),
    light: firstString(display?.light, snapshot.light_level),
    terrain: firstString(display?.terrain, snapshot.terrain_condition),
    context: firstString(display?.context, context?.label, context?.exposure),
    hazards: hazards.length ? hazards.map((hazard) => firstString(recordValue(hazard)?.label, recordValue(hazard)?.name, recordValue(hazard)?.id, hazard)).filter(Boolean).join(', ') : undefined,
  });
}

/** The world as the campaign knows it now: what it does not know is left out, not shown as missing. */
function environmentRowsFromValues(values: Record<string, string | undefined>): RpgWorldStateRowPreview[] {
  const rows: Array<[string, string, string | undefined]> = [
    ['☀', 'Calendar / Season', values.season],
    ['◷', 'Day / Time', values.dayTime],
    ['⌖', 'Region', values.region],
    ['≋', 'Weather', values.weather],
    ['❄', 'Temperature', values.temperature],
    ['↝', 'Wind', values.wind],
    ['◌', 'Visibility', values.visibility],
    ['✦', 'Light', values.light],
    ['▧', 'Terrain', values.terrain],
    ['⌂', 'Context', values.context],
    ['⚠', 'Hazards', values.hazards],
  ];
  return rows.filter((row): row is [string, string, string] => Boolean(row[2])).map(([icon, label, value]) => ({ icon, label, value }));
}

function buildNpcRelationships(session: RpgSession | undefined): RpgNpcRelationshipPreview[] {
  if (!session) return npcRelationships;
  const roots = getSessionRecords(session);
  const candidates = roots.flatMap((root) => [root.npc_relationships, root.relationships, root.social_state, root.social, recordValue(root.npcs)?.relationships, recordValue(root.memory)?.npc_relationships]);
  const relationshipArray = firstArray(...candidates);
  const relationshipRecord = relationshipArray.length ? undefined : firstRecord(...candidates);
  const relationshipItems = relationshipArray.length
    ? relationshipArray
    : relationshipRecord
      ? Object.entries(relationshipRecord).map(([name, value]) => ({ ...(recordValue(value) ?? { score: value }), name }))
      : [];
  if (!relationshipItems.length) return [];
  return relationshipItems.slice(0, 5).map((relationship, index) => {
    const record = recordValue(relationship) ?? { name: relationship };
    const name = firstString(record.name, record.npc, record.character, record.id, record.label) ?? `NPC ${index + 1}`;
    const score = relationshipScore(firstNumber(record.score, record.affinity, record.trust, record.value, record.relationship, record.standing_score));
    const stance = firstString(record.stance, record.status, record.relationship_label, record.label) ?? stanceForScore(score);
    return { name, stance, score };
  });
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
  return { label: 'Latest checkpoint', detail: latestAsset.file_name || latestAsset.id, source: 'live' };
}

function toJobCard(job: RpgJob): RpgJobCardPreview {
  const errorDetail = jobErrorDetail(job);
  return {
    id: String(job.id),
    title: String(job.type),
    status: String(job.status),
    progress: progressPercent(job.progress),
    detail: job.stages?.map((stage) => stage.label).join(' / ') || String(job.resource_class),
    ...(errorDetail ? { errorDetail } : {}),
    source: 'live',
  };
}

function compareRpgJobsForCards(left: RpgJob, right: RpgJob): number {
  const leftActiveRank = activeJobRank(left.status);
  const rightActiveRank = activeJobRank(right.status);
  if (leftActiveRank !== rightActiveRank) return leftActiveRank - rightActiveRank;
  const leftUpdated = timestampRank(firstString(left.updated_at, left.created_at));
  const rightUpdated = timestampRank(firstString(right.updated_at, right.created_at));
  if (leftUpdated !== rightUpdated) return rightUpdated - leftUpdated;
  return String(left.id).localeCompare(String(right.id));
}

function activeJobRank(status: unknown): number {
  const normalized = String(status ?? '').toLowerCase();
  return ['queued', 'running', 'pending'].includes(normalized) ? 0 : 1;
}

function jobErrorDetail(job: RpgJob): string | undefined {
  const jobError = recordValue(job.error);
  const stageError = job.stages?.map((stage) => recordValue(stage.error)).find(Boolean);
  return firstString(
    jobError?.message,
    jobError?.code,
    stageError?.message,
    stageError?.code,
  );
}
