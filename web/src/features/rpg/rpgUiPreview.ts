import type { RpgGearPreview, RpgHeroSummaryPreview, RpgHotbarAbilityPreview, RpgInventoryItemPreview, RpgJobCardPreview, RpgJournalDetailPreview, RpgJournalEntryPreview, RpgNpcRelationshipPreview, RpgPartyMemberPreview, RpgQuestPreview, RpgQuickActionPreview, RpgSessionSummaryPreview, RpgStatPreview, RpgSurvivalPreview, RpgWorldStateRowPreview } from './rpgUiTypes';

export const NOT_TRACKED = 'Not tracked yet';

export const previewHeroSummary: RpgHeroSummaryPreview = {
  avatar: 'A',
  name: 'Alyndra',
  subtitle: 'Level 14 • Ranger',
  origin: 'Wanderer of the North',
  xpLabel: '7,450 / 12,000',
  xpPercent: 62,
  gold: '1,248',
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
  { key: '1', icon: '✦', label: 'Aimed Shot', abilityId: 'recon_aimed_shot', description: 'Take careful aim and turn position into a decisive opening.' },
  { key: '2', icon: '↯', label: 'Frost Arrow', abilityId: 'recon_frost_arrow', description: 'Slow a dangerous target and create a safer window to move.' },
  { key: '3', icon: '☘', label: 'Camouflage', abilityId: 'recon_camouflage', description: 'Blend into terrain and improve stealth or ambush positioning.' },
  { key: '4', icon: '✹', label: 'Radiant Flare', abilityId: 'recon_radiant_flare', description: 'Reveal threats and briefly control the surrounding ground.' },
  { key: '5', icon: '⟡', label: 'Volley', abilityId: 'recon_volley', description: 'Pressure several targets with a rapid spread of arrows.' },
  { key: '6', icon: '⇥', label: 'Dash', abilityId: 'recon_dash', description: 'Spend stamina to cross dangerous ground quickly.' },
];

export const previewSurvival: RpgSurvivalPreview = {
  actions: [
    { label: 'Eat', icon: 'E', command: 'I eat rations' },
    { label: 'Drink', icon: 'D', command: 'I drink water' },
    { label: 'Rest', icon: 'R', command: 'I rest' },
  ],
  detail: 'Hunger, thirst and fatigue rise as time passes; eat, drink and rest to ease them.',
  needs: [
    { id: 'hunger', label: 'Hunger', percent: 24, severity: 'stable', value: '24 / 100' },
    { id: 'thirst', label: 'Thirst', percent: 18, severity: 'stable', value: '18 / 100' },
    { id: 'fatigue', label: 'Fatigue', percent: 31, severity: 'stable', value: '31 / 100' },
  ],
  source: 'preview',
  status: 'Stable',
  warnings: [],
};

export const previewWorldStateRows: RpgWorldStateRowPreview[] = [
  { icon: '☀', label: 'Calendar / Season', value: 'Early Spring' },
  { icon: '◷', label: 'Day / Time', value: 'Day 18 • 09:42' },
  { icon: '⌖', label: 'Region', value: 'mountain_pass' },
  { icon: '≋', label: 'Weather', value: 'Moderate Windy' },
  { icon: '❄', label: 'Temperature', value: '-12°C' },
  { icon: '↝', label: 'Wind', value: 'Strong' },
  { icon: '◌', label: 'Visibility', value: 'Clear' },
  { icon: '✦', label: 'Light', value: 'Daylight' },
  { icon: '▧', label: 'Terrain', value: 'Dry' },
  { icon: '⌂', label: 'Context', value: 'Outdoor • Exposed' },
  { icon: '⚠', label: 'Hazards', value: NOT_TRACKED },
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
  turnLabel: 'Turn 12',
  checkpointLabel: 'Saved 2m ago',
  sortRank: 0,
  source: 'preview',
};
