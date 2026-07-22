import type {
  RpgAuthoringDocumentBlock,
  RpgAuthoringDocumentPage,
  RpgAuthoringEntityCard,
  RpgAuthoringSection,
} from '../../api/rpgWorldAuthoringClient';
import type { RpgWorldGenerationRun, RpgWorldSummary } from '../../api/rpgWorldLibraryClient';
import { documentAnchors } from './RpgWorldCompletionModels';
import { RpgWorldEntityCard } from './RpgWorldEntityCard';
import { RpgWorldEntityDetail } from './RpgWorldEntityDetail';
import { RpgWorldGenerationDashboard } from './RpgWorldGenerationDashboard';
import { RpgWorldLoreLayout } from './RpgWorldLoreLayout';
import { RpgWorldOverviewDashboard } from './RpgWorldOverviewDashboard';
import './RpgWorldDesignFixtures.css';

export type RpgWorldDesignFixtureView =
  | 'overview'
  | 'generation'
  | 'realm'
  | 'history'
  | 'collection'
  | 'entity';

export interface RpgWorldDesignChecklistItem {
  route: string;
  fixture: RpgWorldDesignFixtureView;
  requirements: string[];
}

export const RPG_WORLD_DESIGN_CHECKLIST: RpgWorldDesignChecklistItem[] = [
  {
    route: 'World → Overview',
    fixture: 'overview',
    requirements: ['cinematic hero', 'statistics', 'featured content', 'activity', 'generation summary'],
  },
  {
    route: 'World → Generation',
    fixture: 'generation',
    requirements: ['functional primary actions', 'topic board', 'provider route', 'diagnostics', 'image status'],
  },
  {
    route: 'Lore → Realm Overview',
    fixture: 'realm',
    requirements: ['reading hero', 'pull quote', 'titled prose', 'related canon', 'sticky contents'],
  },
  {
    route: 'Lore → History',
    fixture: 'history',
    requirements: ['chronicle treatment', 'era sequence', 'cause and consequence', 'sticky contents'],
  },
  {
    route: 'World → Collection',
    fixture: 'collection',
    requirements: ['compact summaries', 'featured state', 'visual taxonomy', 'detail action'],
  },
  {
    route: 'World → Collection → Entity',
    fixture: 'entity',
    requirements: ['full-page hero', 'quote', 'quick facts', 'multi-paragraph sections', 'related entries'],
  },
];

export const RPG_WORLD_DESIGN_BREAKPOINTS = [1440, 1024, 768, 390] as const;

const WORLD: RpgWorldSummary = {
  id: 'fixture:aurelia',
  title: 'Aurelia, the Shattered Crown',
  description: 'A luminous realm divided by old celestial wars, living roads, and rival keepers of forgotten gates.',
  status: 'draft',
  source_mode: 'fixture',
  genre: 'mythic fantasy',
  tone: 'heroic, mysterious, politically tense',
  seed: 1449,
  draft_revision: 7,
  metadata: { campaign_template: 'shattered_crown', fixture: true },
  scenario_count: 3,
  created_at: '2026-07-22T00:00:00Z',
  updated_at: '2026-07-22T06:00:00Z',
};

const SECTION_BASE = {
  dependencies: [],
  required_before_launch: true,
  supports_generation: true,
  supports_images: true,
  supports_entity_editing: true,
  operational_status: 'complete',
  editorial_status: 'reviewed',
};

export const RPG_WORLD_DESIGN_SECTIONS: RpgAuthoringSection[] = [
  { ...SECTION_BASE, id: 'overview', label: 'Overview', group: 'workspace', page_kind: 'document', topic_ids: ['realm_overview'], entity_count: 0 },
  { ...SECTION_BASE, id: 'generation', label: 'World Generation', group: 'workspace', page_kind: 'document', topic_ids: [], entity_count: 0 },
  { ...SECTION_BASE, id: 'regions', label: 'Regions', group: 'world', page_kind: 'collection', topic_ids: ['regions'], entity_kind: 'region', entity_count: 6 },
  { ...SECTION_BASE, id: 'factions', label: 'Factions', group: 'world', page_kind: 'collection', topic_ids: ['factions'], entity_kind: 'faction', entity_count: 8 },
  { ...SECTION_BASE, id: 'npcs', label: 'Characters', group: 'game-master', page_kind: 'collection', topic_ids: ['npcs'], entity_kind: 'npc', entity_count: 14 },
  { ...SECTION_BASE, id: 'realm_overview', label: 'Realm Overview', group: 'lore', page_kind: 'document', topic_ids: ['realm_overview'], entity_count: 2 },
  { ...SECTION_BASE, id: 'history', label: 'History', group: 'lore', page_kind: 'document', topic_ids: ['history'], entity_count: 4 },
  { ...SECTION_BASE, id: 'images', label: 'Images', group: 'workspace', page_kind: 'collection', topic_ids: [], entity_count: 12 },
];

const DOSSIER = {
  schema_version: 'rpg_world_entity_dossier_v1',
  subtitle: 'Last keeper of the lantern road',
  quote: {
    text: 'A road is safe only while someone remembers why it was built.',
    attribution: 'Mira Vale, Warden of Ember Crossing',
  },
  quick_facts: [
    { label: 'Role', value: 'Road warden and mediator' },
    { label: 'Homeland', value: 'The Ember March' },
    { label: 'Allegiance', value: 'Lantern Compact' },
    { label: 'Status', value: 'Missing, presumed active' },
  ],
  sections: [
    {
      id: 'overview',
      title: 'Overview',
      paragraphs: [
        'Mira Vale serves as the public face of the Lantern Compact along the unstable roads of the Ember March. Travelers know her as a patient mediator who can read the behavior of living bridges, while local rulers remember that she has repeatedly refused to let military convenience override civilian safety.',
        'Her disappearance transformed an ordinary border dispute into a crisis of trust. Every faction now claims to be protecting her legacy, yet each interprets that legacy in ways that strengthen its own position and weaken the agreements that once kept the road open.',
      ],
    },
    {
      id: 'backstory',
      title: 'Backstory',
      paragraphs: [
        'Mira inherited the wardenship after the Night of Falling Bells, when an entire caravan vanished between two milestones that had stood twenty paces apart at sunset. She spent the following decade rebuilding the route as a network of witnessed promises rather than a sequence of fortified checkpoints.',
        'That history made her valuable to merchants, refugees, and minor nobles who lacked the force to protect themselves. It also made her an obstacle to powers that preferred the March divided into private toll roads and isolated strongholds.',
      ],
    },
    {
      id: 'current-situation',
      title: 'Current Situation',
      paragraphs: [
        'Evidence suggests Mira entered the sealed observatory beneath Ember Crossing shortly before the road began changing direction. No body was found, and the lantern she carried continues to appear in distant windows during storms, always one night before another agreement collapses.',
        'Recovering her would settle several immediate disputes, but learning why she vanished may reveal that the road itself has begun enforcing promises according to an older and less merciful interpretation of the Compact.',
      ],
    },
  ],
  related_entity_ids: ['faction:lantern_compact', 'location:ember_crossing', 'region:ember_march'],
};

export const RPG_WORLD_DESIGN_ENTITY: RpgAuthoringEntityCard = {
  id: 'npc:mira_vale',
  title: 'Mira Vale',
  summary: 'A road warden whose disappearance threatens the agreements that keep the Ember March connected.',
  short_summary: 'A road warden whose disappearance threatens the agreements that keep the Ember March connected.',
  dossier: DOSSIER,
  kind: 'npc',
  card_type: 'npcs',
  presentation: {
    variant: 'npcs',
    eyebrow: 'Featured character',
    badges: ['Warden', 'Lantern Compact', 'Missing'],
    highlights: [
      { label: 'Home', value: 'Ember Crossing' },
      { label: 'Priority', value: 'Keep the living road open' },
    ],
    groups: [
      { label: 'Relationships', items: ['faction:lantern_compact', 'location:ember_crossing'], style: 'chips' },
    ],
  },
  metadata: {
    id: 'npc:mira_vale',
    name: 'Mira Vale',
    kind: 'npc',
    featured: true,
    faction_ids: ['faction:lantern_compact'],
    location_id: 'location:ember_crossing',
    dossier: DOSSIER,
  },
};

const REGION_ENTITY: RpgAuthoringEntityCard = {
  id: 'region:ember_march',
  title: 'The Ember March',
  summary: 'A borderland of red grass, observatory ruins, and roads that remember broken promises.',
  short_summary: 'A borderland of red grass, observatory ruins, and roads that remember broken promises.',
  kind: 'region',
  card_type: 'regions',
  presentation: {
    variant: 'regions',
    eyebrow: 'Featured region',
    badges: ['Frontier', 'Living roads'],
    highlights: [
      { label: 'Capital', value: 'Ember Crossing' },
      { label: 'Pressure', value: 'Competing toll claims' },
    ],
    groups: [],
  },
  metadata: { id: 'region:ember_march', name: 'The Ember March', kind: 'region', featured: true },
};

const FACTION_ENTITY: RpgAuthoringEntityCard = {
  id: 'faction:lantern_compact',
  title: 'The Lantern Compact',
  summary: 'Wardens, witnesses, and caravan masters who keep travel agreements visible and enforceable.',
  short_summary: 'Wardens, witnesses, and caravan masters who keep travel agreements visible and enforceable.',
  kind: 'faction',
  card_type: 'factions',
  presentation: {
    variant: 'factions',
    eyebrow: 'Key faction',
    badges: ['Neutral', 'Road wardens'],
    highlights: [
      { label: 'Leader', value: 'Mira Vale' },
      { label: 'Goal', value: 'Restore witnessed passage' },
    ],
    groups: [],
  },
  metadata: { id: 'faction:lantern_compact', name: 'The Lantern Compact', kind: 'faction' },
};

export const RPG_WORLD_DESIGN_COLLECTION = [RPG_WORLD_DESIGN_ENTITY, REGION_ENTITY, FACTION_ENTITY];

const REALM_BLOCKS: RpgAuthoringDocumentBlock[] = [
  {
    kind: 'section',
    title: 'The Shattered Crown',
    body: 'Aurelia is not ruled by a single monarch. Its crown survives as seven celestial fragments whose light legitimizes laws, wakes ancient roads, and alters the memories recorded in stone.\n\nEach fragment answers to a different idea of sovereignty, forcing rulers to negotiate with the symbols they claim to possess.',
  },
  {
    kind: 'section',
    title: 'Major Powers',
    body: 'The Lantern Compact protects movement between rival territories, while the Glass Synod controls the observatories used to interpret the crown fragments.\n\nNeither organization can dominate the realm alone, and their uneasy cooperation defines most public stability.',
  },
  {
    kind: 'section',
    title: 'Important Places',
    body: 'Ember Crossing anchors the eastern road network. The Hollow Meridian marks the boundary where maps cease to agree, and the Crownfall Basin contains the brightest surviving fragment.\n\nTravel among these places is both a geographic journey and a negotiation with remembered promises.',
  },
];

const HISTORY_BLOCKS: RpgAuthoringDocumentBlock[] = [
  {
    kind: 'section',
    title: 'The Concordant Age',
    body: 'For three centuries the crown fragments were carried together during the annual procession, allowing roads, calendars, and legal memory to remain synchronized.\n\nThe system depended on witnessed cooperation rather than centralized force, and its rituals became the basis of regional identity.',
  },
  {
    kind: 'section',
    title: 'The Night of Falling Bells',
    body: 'The procession failed when every bell in the capital sounded a different hour. The fragments separated, roads folded across one another, and several institutions preserved incompatible versions of the same decree.\n\nModern disputes still inherit legal claims created during that single night.',
  },
  {
    kind: 'section',
    title: 'The Present Fracture',
    body: 'Current rulers seek reunification without agreeing on which historical record should become authoritative. Smaller communities instead preserve local agreements and fear that a restored crown would erase the compromises that allowed them to survive.\n\nThe campaign begins as those competing futures become impossible to postpone.',
  },
];

const OVERVIEW_PAGE: RpgAuthoringDocumentPage = {
  ok: true,
  section_id: 'overview',
  page_kind: 'document',
  title: WORLD.title,
  summary: WORLD.description,
  body: REALM_BLOCKS,
  related_entities: [REGION_ENTITY as unknown as Record<string, unknown>, FACTION_ENTITY as unknown as Record<string, unknown>, RPG_WORLD_DESIGN_ENTITY as unknown as Record<string, unknown>],
};

const GENERATION_RUN: RpgWorldGenerationRun = {
  run_id: 'fixture:world-generation:aurelia',
  world_id: WORLD.id,
  draft_revision: WORLD.draft_revision,
  status: 'running',
  graph: {},
  context: { resolved_provider_source: 'settings_control_center' },
  settings: { provider_route: 'lmstudio', model: 'qwen-world-forge' },
  plan: { topic_ids: RPG_WORLD_DESIGN_SECTIONS.filter((section) => section.supports_generation).map((section) => section.id) },
  progress: {
    percent: 68,
    active_topic_ids: ['history'],
    failed_topic_ids: [],
    completed_topics: 5,
    total_topics: 8,
  },
  error: {},
  created_at: '2026-07-22T05:30:00Z',
  updated_at: '2026-07-22T06:00:00Z',
};

export interface RpgWorldDesignFixtureCanvasProps {
  view: RpgWorldDesignFixtureView;
}

export function RpgWorldDesignFixtureCanvas({ view }: RpgWorldDesignFixtureCanvasProps) {
  if (view === 'overview') {
    return (
      <RpgWorldOverviewDashboard
        onEdit={() => undefined}
        onOpenSection={() => undefined}
        page={OVERVIEW_PAGE}
        sections={RPG_WORLD_DESIGN_SECTIONS}
        world={WORLD}
      />
    );
  }
  if (view === 'generation') {
    return (
      <RpgWorldGenerationDashboard
        generation={GENERATION_RUN}
        onOpenImages={() => undefined}
        onOpenSection={() => undefined}
        sections={RPG_WORLD_DESIGN_SECTIONS}
        worldId={WORLD.id}
      />
    );
  }
  if (view === 'realm' || view === 'history') {
    const blocks = view === 'history' ? HISTORY_BLOCKS : REALM_BLOCKS;
    return (
      <RpgWorldLoreLayout
        blocks={blocks}
        sectionId={view === 'history' ? 'history' : 'realm_overview'}
        summary={view === 'history' ? 'A chronicle of the agreements, fractures, and unresolved claims that shaped modern Aurelia.' : WORLD.description}
        title={view === 'history' ? 'History of Aurelia' : 'Realm Overview'}
        toc={documentAnchors(blocks)}
      />
    );
  }
  if (view === 'entity') {
    return (
      <RpgWorldEntityDetail
        entity={RPG_WORLD_DESIGN_ENTITY}
        onClose={() => undefined}
        onOpenRelated={() => undefined}
        worldId={WORLD.id}
      />
    );
  }
  return (
    <section className="rpg-world-design-fixture-collection">
      <header><p className="eyebrow">Deterministic fixture</p><h2>World Collection</h2><span>{RPG_WORLD_DESIGN_COLLECTION.length} entries</span></header>
      <div className="rpg-authoring-entity-grid">
        {RPG_WORLD_DESIGN_COLLECTION.map((entity) => (
          <RpgWorldEntityCard entity={entity} key={entity.id} onOpen={() => undefined} worldId={WORLD.id} />
        ))}
      </div>
    </section>
  );
}
