import type { RpgPlaySectionsDraft, RpgPlaySectionsReferences } from './api/rpgWorldPlaySectionsClient';

/**
 * The fields of each play section (RQ-4.1), as the world editor's form shows them. A section is a list of rows; a
 * field names a person, place, item, creature, region or quest of the world by its id (``ref``). New rows start as
 * the server's own defaults (``world_play_sections.py``), with an id of their own.
 */
export type RefKind = keyof RpgPlaySectionsReferences;
export type PlayRow = Record<string, unknown>;
export type PlaySectionId = 'economy' | 'routines' | 'knowledge' | 'pressures' | 'bestiary' | 'quests';
export type NameOf = (id: unknown) => string;

export type PlayField =
  | { key: string; label: string; kind: 'text' | 'textarea' }
  | { key: string; label: string; kind: 'number'; min?: number; max?: number; step?: number; nullable?: boolean }
  | { key: string; label: string; kind: 'select'; options: Array<[string, string]>; nullable?: string }
  | { key: string; label: string; kind: 'ref'; refs: RefKind[]; optional?: string }
  | { key: string; label: string; kind: 'tags' }
  | { key: string; label: string; kind: 'price'; nullable?: boolean }
  | { key: string; label: string; kind: 'lever' }
  | { key: string; label: string; kind: 'subject'; by: string }
  | { key: string; label: string; kind: 'list'; rows: PlayRows }
  | { key: string; label: string; kind: 'group'; fields: PlayField[]; blank: () => PlayRow };

export interface PlayRows {
  fields: PlayField[];
  blank: (siblings: PlayRow[]) => PlayRow;
  title: (row: PlayRow, name: NameOf) => string;
  add: string;
}

export interface PlaySection {
  id: PlaySectionId;
  label: string;
  summary: string;
  rows: PlayRows;
  read: (draft: RpgPlaySectionsDraft) => PlayRow[];
  write: (draft: RpgPlaySectionsDraft, rows: PlayRow[]) => RpgPlaySectionsDraft;
}

const HOURS = { min: 0, max: 24, step: 1 };

function nextId(prefix: string, siblings: PlayRow[], key: string): string {
  const taken = new Set(siblings.map((row) => String(row[key] ?? '')));
  let index = siblings.length + 1;
  while (taken.has(`${prefix}-${index}`)) index += 1;
  return `${prefix}-${index}`;
}

function text(value: unknown, fallback: string): string {
  return typeof value === 'string' && value.trim() ? value : fallback;
}

const OFFER: PlayRows = {
  fields: [
    { key: 'name', label: 'Name', kind: 'text' },
    { key: 'service', label: 'Service', kind: 'select', options: [
      ['shop_goods', 'Goods'], ['lodging', 'Lodging'], ['meal', 'Meal'], ['drink', 'Drink'], ['repair', 'Repair'],
      ['paid_information', 'Information'],
    ] },
    { key: 'item_id', label: 'Item sold (goods)', kind: 'ref', refs: ['items'], optional: 'None' },
    { key: 'price', label: 'Price', kind: 'price' },
    { key: 'stock', label: 'Stock (blank: never runs out)', kind: 'number', min: 0, nullable: true },
    { key: 'restock_per_day', label: 'Restocks per day', kind: 'number', min: 0 },
    { key: 'description', label: 'Description', kind: 'textarea' },
    { key: 'offer_key', label: 'Offer key', kind: 'text' },
  ],
  blank: (siblings) => ({ offer_key: nextId('offer', siblings, 'offer_key'), service: 'shop_goods', name: '',
    description: '', price: { gold: 0, silver: 1, copper: 0 }, item_id: '', stock: null, restock_per_day: 0 }),
  title: (row) => text(row.name, 'New offer'),
  add: 'Add offer',
};

const PROVIDERS: PlayRows = {
  fields: [
    { key: 'provider_id', label: 'Seller', kind: 'ref', refs: ['people'] },
    { key: 'location_id', label: 'Where they sell', kind: 'ref', refs: ['places'], optional: 'Where they are found' },
    { key: 'sells', label: 'Sells', kind: 'list', rows: OFFER },
    { key: 'buys', label: 'Buys back', kind: 'group', blank: () => ({ item_types: [], price_fraction: 0.5 }), fields: [
      { key: 'item_types', label: 'Item types (comma separated)', kind: 'tags' },
      { key: 'price_fraction', label: 'Share of the price paid', kind: 'number', min: 0, max: 1, step: 0.05 },
    ] },
  ],
  blank: () => ({ provider_id: '', location_id: '', sells: [], buys: null }),
  title: (row, name) => name(row.provider_id),
  add: 'Add seller',
};

const SCHEDULE: PlayRows = {
  fields: [
    { key: 'from_hour', label: 'From hour', kind: 'number', ...HOURS },
    { key: 'to_hour', label: 'To hour', kind: 'number', ...HOURS },
    { key: 'location_id', label: 'Where', kind: 'ref', refs: ['places'] },
    { key: 'activity', label: 'Doing', kind: 'text' },
  ],
  blank: () => ({ from_hour: 8, to_hour: 20, location_id: '', activity: '' }),
  title: (row, name) => `${String(row.from_hour ?? 0)}:00–${String(row.to_hour ?? 24)}:00 · ${name(row.location_id)}`,
  add: 'Add hours',
};

const GOALS: PlayRows = {
  fields: [
    { key: 'summary', label: 'Goal', kind: 'textarea' },
    { key: 'priority', label: 'Priority (5 leads)', kind: 'number', min: 1, max: 5 },
    { key: 'topics', label: 'Topics that touch it (comma separated)', kind: 'tags' },
    { key: 'location_id', label: 'Where it leads them', kind: 'ref', refs: ['places'], optional: 'Nowhere in particular' },
    { key: 'goal_id', label: 'Goal id', kind: 'text' },
  ],
  blank: (siblings) => ({ goal_id: nextId('goal', siblings, 'goal_id'), summary: '', priority: 3, topics: [], location_id: '' }),
  title: (row) => text(row.summary, 'New goal'),
  add: 'Add goal',
};

const ROUTINES: PlayRows = {
  fields: [
    { key: 'npc_id', label: 'Person', kind: 'ref', refs: ['people'] },
    { key: 'schedule', label: 'Their day', kind: 'list', rows: SCHEDULE },
    { key: 'goals', label: 'Goals', kind: 'list', rows: GOALS },
  ],
  blank: () => ({ npc_id: '', schedule: [], goals: [] }),
  title: (row, name) => name(row.npc_id),
  add: 'Add person',
};

const FACTS: PlayRows = {
  fields: [
    { key: 'text', label: 'What they know', kind: 'textarea' },
    { key: 'shares', label: 'Shares it', kind: 'select', options: [
      ['freely', 'Freely'], ['for_price', 'For a price'], ['when_trusted', 'When trusted'], ['never', 'Never'],
    ] },
    { key: 'price', label: 'Price (for a price)', kind: 'price', nullable: true },
    { key: 'trust_needed', label: 'Trust needed (0–100)', kind: 'number', min: 0, max: 100 },
    { key: 'topics', label: 'Topics (comma separated)', kind: 'tags' },
    { key: 'fact_id', label: 'Fact id', kind: 'text' },
  ],
  blank: (siblings) => ({ fact_id: nextId('fact', siblings, 'fact_id'), text: '', shares: 'freely', price: null,
    trust_needed: 0, topics: [] }),
  title: (row) => text(row.text, 'New fact'),
  add: 'Add fact',
};

const KNOWLEDGE: PlayRows = {
  fields: [
    { key: 'npc_id', label: 'Person', kind: 'ref', refs: ['people'] },
    { key: 'facts', label: 'Knows', kind: 'list', rows: FACTS },
  ],
  blank: () => ({ npc_id: '', facts: [] }),
  title: (row, name) => name(row.npc_id),
  add: 'Add person',
};

const LEVERS: PlayRows = {
  fields: [
    { key: 'action', label: 'Pulled by', kind: 'lever' },
    { key: 'effect', label: 'Effect', kind: 'select', options: [['lower', 'Eases it'], ['raise', 'Worsens it']] },
    { key: 'amount', label: 'By', kind: 'number', min: 0.5, max: 100, step: 0.5 },
  ],
  blank: () => ({ action: 'defeat:', effect: 'lower', amount: 5 }),
  title: (row, name) => {
    const [kind, subject] = String(row.action ?? '').split(/:(.*)/s);
    return `${kind === 'quest' ? 'Finishing' : 'Defeating'} ${name(subject)}`;
  },
  add: 'Add lever',
};

const PRESSURES: PlayRows = {
  fields: [
    { key: 'name', label: 'Name', kind: 'text' },
    { key: 'description', label: 'Description', kind: 'textarea' },
    { key: 'region_id', label: 'Where it bears', kind: 'ref', refs: ['regions', 'places'] },
    { key: 'dimension', label: 'What it wears down', kind: 'select', options: [
      ['political_stability', 'Who governs'], ['trade_access', 'Trade'], ['resource_access', 'Resources'],
      ['population_index', 'The people'],
    ] },
    { key: 'severity', label: 'Severity (0–100)', kind: 'number', min: 0, max: 100 },
    { key: 'trend', label: 'Trend', kind: 'select', options: [
      ['escalating', 'Escalating'], ['volatile', 'Volatile'], ['contained', 'Contained'], ['stable', 'Stable'],
    ] },
    { key: 'escalation_threshold', label: 'Boils over at', kind: 'number', min: 0, max: 100 },
    { key: 'resolution_threshold', label: 'Resolved below', kind: 'number', min: 0, max: 100 },
    { key: 'levers', label: 'What the hero can do about it', kind: 'list', rows: LEVERS },
    { key: 'pressure_id', label: 'Pressure id', kind: 'text' },
  ],
  blank: (siblings) => ({ pressure_id: nextId('pressure', siblings, 'pressure_id'), name: '', description: '',
    region_id: '', dimension: 'political_stability', severity: 40, trend: 'escalating', escalation_threshold: 75,
    resolution_threshold: 15, levers: [] }),
  title: (row) => text(row.name, 'New pressure'),
  add: 'Add pressure',
};

const LOOT: PlayRows = {
  fields: [
    { key: 'item_id', label: 'Item', kind: 'ref', refs: ['items'] },
    { key: 'chance', label: 'Chance (0–1)', kind: 'number', min: 0.01, max: 1, step: 0.01 },
    { key: 'quantity', label: 'Quantity', kind: 'number', min: 1, max: 99 },
  ],
  blank: () => ({ item_id: '', chance: 0.25, quantity: 1 }),
  title: (row, name) => name(row.item_id),
  add: 'Add drop',
};

const BESTIARY: PlayRows = {
  fields: [
    { key: 'id', label: 'Creature', kind: 'ref', refs: ['creatures'] },
    { key: 'behaviour', label: 'Behaviour', kind: 'select', nullable: 'As its lore tells', options: [
      ['fights', 'Fights'], ['flees_when_hurt', 'Flees when hurt'], ['calls_allies', 'Calls allies'],
      ['guards', 'Guards'], ['ambushes', 'Ambushes'],
    ] },
    { key: 'stats', label: 'Numbers', kind: 'group', blank: () => ({ level: 1, hp: 10, defense: 10, damage_min: 1,
      damage_max: 4, accuracy_bonus: 0, xp_value: 25 }), fields: [
      { key: 'level', label: 'Level', kind: 'number', min: 1, max: 30 },
      { key: 'hp', label: 'Health', kind: 'number', min: 1, max: 1000 },
      { key: 'defense', label: 'Defense', kind: 'number', min: 1, max: 40 },
      { key: 'damage_min', label: 'Damage from', kind: 'number', min: 0, max: 200 },
      { key: 'damage_max', label: 'Damage to', kind: 'number', min: 1, max: 200 },
      { key: 'accuracy_bonus', label: 'Accuracy', kind: 'number', min: -5, max: 20 },
      { key: 'xp_value', label: 'Experience', kind: 'number', min: 0, max: 10000 },
    ] },
    { key: 'loot', label: 'Drops', kind: 'list', rows: LOOT },
  ],
  blank: () => ({ id: '', stats: null, behaviour: null, loot: [] }),
  title: (row, name) => name(row.id),
  add: 'Add creature',
};

/** What a quest condition's subject is chosen from, by the condition's kind (a check names its kind instead). */
export const CONDITION_SUBJECTS: Record<string, RefKind | null> = {
  reach: 'places', talk: 'people', hold: 'items', defeat: 'creatures', companion: 'people', check: null,
};

/** The checks a step may ask (``rules/checks.py``). */
export const CHECK_KINDS: Array<[string, string]> = [
  ['persuade', 'Persuade'], ['intimidate', 'Intimidate'], ['deceive', 'Deceive'], ['haggle', 'Haggle'],
  ['sneak', 'Sneak'], ['climb', 'Climb'], ['pick_lock', 'Pick a lock'], ['recall_lore', 'Recall lore'],
  ['search', 'Search'], ['notice', 'Notice'],
];

const CONDITION_VERBS: Record<string, string> = {
  reach: 'Reach', talk: 'Talk to', hold: 'Hold', defeat: 'Defeat', check: 'Pass a check to', companion: 'Travel with',
};

function conditionText(row: PlayRow, name: NameOf): string {
  const kind = String(row.kind ?? '');
  const check = CHECK_KINDS.find(([value]) => value === row.subject);
  const subject = kind === 'check' ? (check ? check[1].toLowerCase() : text(row.subject, 'do something'))
    : kind === 'companion' && row.subject === 'anyone' ? 'a companion' : name(row.subject);
  const count = kind === 'defeat' && Number(row.count ?? 1) > 1 ? `${String(row.count)} × ` : '';
  const about = kind === 'talk' && Array.isArray(row.about) && row.about.length ? ` about ${row.about.join(' / ')}` : '';
  return `${CONDITION_VERBS[kind] ?? 'Do'} ${count}${subject}${about}`;
}

const CONDITIONS: PlayRows = {
  fields: [
    { key: 'kind', label: 'What it asks', kind: 'select', options: [
      ['reach', 'Reach a place'], ['talk', 'Talk to someone'], ['hold', 'Hold an item'], ['defeat', 'Defeat a creature'],
      ['check', 'Pass a check'], ['companion', 'Travel with a companion'],
    ] },
    { key: 'subject', label: 'Of', kind: 'subject', by: 'kind' },
    { key: 'about', label: 'About (talk: any of these words, comma separated)', kind: 'tags' },
    { key: 'count', label: 'How many (defeat)', kind: 'number', min: 1, max: 50 },
    { key: 'target', label: 'Against (check)', kind: 'ref', refs: ['people'], optional: 'Whoever is there' },
  ],
  blank: () => ({ kind: 'reach', subject: '', about: [], count: 1, target: '' }),
  title: conditionText,
  add: 'Add condition',
};

const WAYS: PlayRows = {
  fields: [{ key: 'conditions', label: 'All of', kind: 'list', rows: CONDITIONS }],
  blank: () => ({ conditions: [CONDITIONS.blank([])] }),
  title: (row, name) => rowsOf(row.conditions).map((condition) => conditionText(condition, name)).join(' and ') || 'New way',
  add: 'Add another way (a branch)',
};

const STEPS: PlayRows = {
  fields: [
    { key: 'summary', label: 'What the hero is told', kind: 'textarea' },
    { key: 'ways', label: 'Done by any one of', kind: 'list', rows: WAYS },
    { key: 'id', label: 'Step id', kind: 'text' },
  ],
  blank: (siblings) => ({ id: nextId('step', siblings, 'id'), summary: '', ways: [WAYS.blank([])] }),
  title: (row) => text(row.summary, 'New step'),
  add: 'Add step',
};

const QUESTS: PlayRows = {
  fields: [
    { key: 'id', label: 'Quest', kind: 'ref', refs: ['quests'] },
    { key: 'giver_id', label: 'Given by', kind: 'ref', refs: ['people'], optional: 'No one in particular' },
    { key: 'deadline_hours', label: 'Deadline in hours (blank: none)', kind: 'number', min: 1, nullable: true },
    { key: 'steps', label: 'Steps, in order', kind: 'list', rows: STEPS },
  ],
  blank: () => ({ id: '', giver_id: '', deadline_hours: null, steps: [] }),
  title: (row, name) => name(row.id),
  add: 'Add quest',
};

function rowsOf(value: unknown): PlayRow[] {
  return Array.isArray(value) ? value as PlayRow[] : [];
}

export const PLAY_SECTIONS: PlaySection[] = [
  {
    id: 'economy', label: 'Economy', summary: 'Who sells what, at what price and stock, and what they buy back.',
    rows: PROVIDERS,
    read: (draft) => rowsOf(draft.economy?.providers),
    write: (draft, rows) => ({ ...draft, economy: { ...draft.economy, providers: rows as never } }),
  },
  {
    id: 'routines', label: 'Routines', summary: 'Where each person is through the day, and what they are after.',
    rows: ROUTINES,
    read: (draft) => rowsOf(draft.routines),
    write: (draft, rows) => ({ ...draft, routines: rows as never }),
  },
  {
    id: 'knowledge', label: 'Knowledge', summary: 'What each person knows, and on what terms they tell it.',
    rows: KNOWLEDGE,
    read: (draft) => rowsOf(draft.knowledge),
    write: (draft, rows) => ({ ...draft, knowledge: rows as never }),
  },
  {
    id: 'pressures', label: 'Pressures', summary: 'The forces the world’s clock moves, and what eases or worsens them.',
    rows: PRESSURES,
    read: (draft) => rowsOf(draft.pressures),
    write: (draft, rows) => ({ ...draft, pressures: rows as never }),
  },
  {
    id: 'bestiary', label: 'Bestiary', summary: 'How the world’s creatures fight, and what they drop.',
    rows: BESTIARY,
    read: (draft) => rowsOf(draft.bestiary),
    write: (draft, rows) => ({ ...draft, bestiary: rows as never }),
  },
  {
    id: 'quests', label: 'Quests', summary: 'What each quest takes, step by step, and where it branches; a quest left out is done by reaching its places.',
    rows: QUESTS,
    read: (draft) => rowsOf(draft.quests),
    write: (draft, rows) => ({ ...draft, quests: rows as never }),
  },
];

/** What a release finding means, for the author: ``play_section_unknown_person:routines:npc:x`` and the like. */
export function describeFinding(finding: string, name: NameOf): string {
  const [code, section, ...rest] = finding.split(':');
  const subject = rest.join(':');
  const what: Record<string, string> = {
    play_section_unknown_person: 'names a person the world does not have',
    play_section_unknown_place: 'names a place the world does not have',
    play_section_unknown_item: 'names an item the world does not have',
    play_section_unknown_creature: 'names a creature the world does not have',
    play_section_unknown_lever: 'is pulled by something the world does not have',
    play_section_unknown_quest: 'names a quest the world does not have',
    play_section_unknown_check: 'asks a check the game does not have',
  };
  const label = section ? section.charAt(0).toUpperCase() + section.slice(1).replace(/\..*$/, '') : 'A section';
  if (what[code]) return `${label} ${what[code]}: ${name(subject)}`;
  return finding.replace(/^play_section_invalid:/, 'Not valid: ');
}
