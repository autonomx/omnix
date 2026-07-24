import type {
  RpgAuthoringDocumentBlock,
  RpgAuthoringSection,
} from '../../api/rpgWorldAuthoringClient';

export interface RpgWorldEditorRoute {
  worldId: string;
  sectionId: string;
  entityId?: string;
}

const AUTHORING_GROUP_ORDER: RpgAuthoringSection['group'][] = [
  'workspace',
  'world',
  'lore',
  'game-master',
];

export function completeAuthoringSections(sections: RpgAuthoringSection[]): RpgAuthoringSection[] {
  const groupRank = new Map(AUTHORING_GROUP_ORDER.map((group, index) => [group, index]));
  return sections
    .map((section, index) => ({ section, index }))
    .sort((left, right) => {
      const groupDifference = (groupRank.get(left.section.group) ?? 99)
        - (groupRank.get(right.section.group) ?? 99);
      return groupDifference || left.index - right.index;
    })
    .map(({ section }) => section);
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
