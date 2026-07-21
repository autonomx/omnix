import type {
  RpgAuthoringDocumentBlock,
  RpgAuthoringSection,
} from '../../api/rpgWorldAuthoringClient';

export interface RpgWorldEditorRoute {
  worldId: string;
  sectionId: string;
  entityId?: string;
}

const CANONICAL_LORE: Array<Pick<RpgAuthoringSection, 'id' | 'label' | 'dependencies'>> = [
  { id: 'realm', label: 'Realm Overview', dependencies: [] },
  { id: 'cosmology', label: 'Cosmology and World Laws', dependencies: ['realm'] },
  { id: 'magic_technology', label: 'Magic and Technology', dependencies: ['cosmology'] },
  { id: 'history', label: 'History', dependencies: ['realm', 'cosmology'] },
  { id: 'calendar', label: 'Calendar and Eras', dependencies: ['history'] },
  { id: 'cultures', label: 'Cultures and Peoples', dependencies: ['regions', 'history'] },
  { id: 'institutions', label: 'Institutions', dependencies: ['factions', 'cultures'] },
  { id: 'pantheon', label: 'Religions and Pantheon', dependencies: ['cosmology', 'cultures'] },
  { id: 'hero_system', label: 'Heroes, Summoning, and Exceptional Powers', dependencies: ['cosmology', 'magic_technology', 'institutions'] },
  { id: 'current_conflicts', label: 'Current Conflicts', dependencies: ['factions', 'institutions', 'regions'] },
];

function syntheticLoreSection(
  definition: Pick<RpgAuthoringSection, 'id' | 'label' | 'dependencies'>,
): RpgAuthoringSection {
  return {
    ...definition,
    group: 'lore',
    page_kind: 'document',
    topic_ids: [definition.id],
    required_before_launch: true,
    supports_generation: true,
    supports_images: definition.id === 'realm',
    supports_entity_editing: false,
    operational_status: 'waiting',
    editorial_status: 'unreviewed',
    entity_count: 0,
  };
}

export function completeAuthoringSections(sections: RpgAuthoringSection[]): RpgAuthoringSection[] {
  const byId = new Map(sections.map((section) => [section.id, section]));
  const canonicalIds = new Set(CANONICAL_LORE.map((section) => section.id));
  const groups: RpgAuthoringSection[] = [];

  for (const group of ['workspace', 'world'] as const) {
    groups.push(...sections.filter((section) => section.group === group));
  }
  groups.push(...CANONICAL_LORE.map((definition) => byId.get(definition.id) ?? syntheticLoreSection(definition)));
  groups.push(...sections.filter((section) => section.group === 'lore' && !canonicalIds.has(section.id)));
  groups.push(...sections.filter((section) => section.group === 'game-master'));
  return groups;
}

export function parseWorldEditorRoute(search = typeof window === 'undefined' ? '' : window.location.search): RpgWorldEditorRoute | null {
  const query = search.startsWith('?') ? search.slice(1) : search;
  const params = new URLSearchParams(query);
  const worldId = params.get('rpg-world')?.trim() ?? '';
  if (!worldId) return null;
  return {
    worldId,
    sectionId: params.get('section')?.trim() || 'overview',
    entityId: params.get('entity')?.trim() || undefined,
  };
}

export function worldEditorSearch(route: RpgWorldEditorRoute | null, currentSearch = ''): string {
  const params = new URLSearchParams(currentSearch.startsWith('?') ? currentSearch.slice(1) : currentSearch);
  params.delete('rpg-world');
  params.delete('section');
  params.delete('entity');
  if (route) {
    params.set('rpg-world', route.worldId);
    params.set('section', route.sectionId || 'overview');
    if (route.entityId) params.set('entity', route.entityId);
  }
  const query = params.toString();
  return query ? `?${query}` : '';
}

export function pushWorldEditorRoute(route: RpgWorldEditorRoute | null, replace = false): void {
  if (typeof window === 'undefined') return;
  const next = `${window.location.pathname}${worldEditorSearch(route, window.location.search)}`;
  if (replace) window.history.replaceState(route, '', next);
  else window.history.pushState(route, '', next);
}

function slug(value: string, fallback: string): string {
  const normalized = value.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
  return normalized || fallback;
}

export function documentAnchors(blocks: RpgAuthoringDocumentBlock[]): Array<{ id: string; label: string }> {
  const counts = new Map<string, number>();
  return blocks.map((block, index) => {
    const label = block.title || block.kind.replace(/[_-]+/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
    const base = slug(label, `section-${index + 1}`);
    const occurrence = counts.get(base) ?? 0;
    counts.set(base, occurrence + 1);
    return { id: occurrence ? `${base}-${occurrence + 1}` : base, label };
  });
}

const CHRONICLE_IDS = new Set(['history', 'calendar', 'calendar_and_eras', 'current_conflicts']);

export function isChronicleSection(sectionId: string): boolean {
  return CHRONICLE_IDS.has(sectionId);
}

export function presentLoreBlocks(
  sectionId: string,
  blocks: RpgAuthoringDocumentBlock[],
): RpgAuthoringDocumentBlock[] {
  if (CHRONICLE_IDS.has(sectionId)) {
    return blocks.map((block) => block.kind === 'json' ? block : { ...block, kind: 'timeline' });
  }
  if (sectionId === 'realm') {
    return blocks.map((block, index) => ({
      ...block,
      kind: block.kind === 'json' ? 'json' : index === 0 ? 'realm-summary' : block.kind,
      title: block.title || (index === 0 ? 'Realm identity' : undefined),
    }));
  }
  return blocks;
}
