import { describe, expect, it } from 'vitest';
import type { RpgAuthoringSection } from '../../api/rpgWorldAuthoringClient';
import {
  completeAuthoringSections,
  documentAnchors,
  parseWorldEditorRoute,
  presentLoreBlocks,
  worldEditorSearch,
} from './RpgWorldCompletionModels';

function section(id: string, group: RpgAuthoringSection['group']): RpgAuthoringSection {
  return {
    id,
    label: id,
    group,
    page_kind: 'document',
    topic_ids: [id],
    dependencies: [],
    required_before_launch: false,
    supports_generation: true,
    supports_images: false,
    supports_entity_editing: false,
    operational_status: 'complete',
    editorial_status: 'unreviewed',
    entity_count: 0,
  };
}

describe('world authoring completion models', () => {
  it('restores every canonical lore section for historical manifests', () => {
    const completed = completeAuthoringSections([
      section('overview', 'workspace'),
      section('realm', 'lore'),
      section('history', 'lore'),
    ]);
    expect(completed.filter((row) => row.group === 'lore').map((row) => row.id)).toEqual([
      'realm',
      'cosmology',
      'magic_technology',
      'history',
      'calendar',
      'cultures',
      'institutions',
      'pantheon',
      'hero_system',
      'current_conflicts',
    ]);
    expect(completed.find((row) => row.id === 'pantheon')?.operational_status).toBe('waiting');
  });

  it('creates unique anchors when lore sections repeat a title', () => {
    expect(documentAnchors([
      { kind: 'section', title: 'Major Powers' },
      { kind: 'facts', title: 'Major Powers' },
      { kind: 'section', title: 'Major Powers' },
    ])).toEqual([
      { id: 'major-powers', label: 'Major Powers' },
      { id: 'major-powers-2', label: 'Major Powers' },
      { id: 'major-powers-3', label: 'Major Powers' },
    ]);
  });

  it('projects history blocks into typed timeline entries', () => {
    const blocks = presentLoreBlocks('history', [
      { kind: 'section', title: 'First Age', body: 'The first age begins.' },
      { kind: 'facts', title: 'Turning Points', items: [{ label: 'The Sundering', statement: 'The realm divides.' }] },
    ]);
    expect(blocks.map((block) => block.kind)).toEqual(['timeline', 'timeline']);
  });

  it('round-trips direct entity routes through query parameters', () => {
    const search = worldEditorSearch({ worldId: 'world:aurelia', sectionId: 'classes', entityId: 'class:warden' }, '?keep=1');
    expect(search).toContain('keep=1');
    expect(parseWorldEditorRoute(search)).toEqual({
      worldId: 'world:aurelia',
      sectionId: 'classes',
      entityId: 'class:warden',
    });
  });
});
