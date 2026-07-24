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
  it('uses only profile-backed sections supplied by the authoring manifest', () => {
    const completed = completeAuthoringSections([
      section('overview', 'workspace'),
      section('networks', 'world'),
      section('augmentations', 'world'),
      section('opening_threads', 'game-master'),
    ]);

    expect(completed.map((row) => row.id)).toEqual([
      'overview',
      'networks',
      'augmentations',
      'opening_threads',
    ]);
    expect(completed.some((row) => row.id === 'spells')).toBe(false);
    expect(completed.some((row) => row.id === 'pantheon')).toBe(false);
    expect(completed.some((row) => row.id === 'hero_system')).toBe(false);
  });

  it('keeps manifest order within each navigation group', () => {
    const completed = completeAuthoringSections([
      section('pressures', 'lore'),
      section('overview', 'workspace'),
      section('actors', 'world'),
      section('places', 'world'),
    ]);

    expect(completed.map((row) => row.id)).toEqual([
      'overview',
      'actors',
      'places',
      'pressures',
    ]);
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
