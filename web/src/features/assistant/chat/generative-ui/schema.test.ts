import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { chatUiBlockSchema, parseChatUi } from './schema';

// The golden fixtures the server's compiler tests also run (resources/chat/generative_ui/fixtures).
const fixturesRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../../../../../../resources/chat/generative_ui/fixtures');

type Fixture = { name: string; content: string; expected: Record<string, unknown> & { segments: Array<Record<string, unknown>>; blocks: Record<string, unknown> } };

function loadFixture(name: string): Fixture {
  return JSON.parse(readFileSync(join(fixturesRoot, `${name}.json`), 'utf8')) as Fixture;
}

const fixtures = readdirSync(fixturesRoot).filter((name) => name.endsWith('.json')).map((name) => loadFixture(name.replace(/\.json$/, '')));

describe('generative UI schema', () => {
  it('reads the shared fixtures', () => {
    expect(fixtures.length).toBeGreaterThanOrEqual(10);
  });

  it.each(fixtures.map((fixture) => [fixture.name, fixture] as const))('accepts the server payload of %s', (_name, fixture) => {
    const parsed = parseChatUi({ ui: fixture.expected }, fixture.content);

    expect(parsed).not.toBeNull();
    expect(parsed?.segments).toHaveLength(fixture.expected.segments.length);
    for (const [index, segment] of fixture.expected.segments.entries()) {
      const rendered = parsed?.segments[index];
      expect(rendered?.kind).toBe(segment.kind);
      if (segment.kind === 'markdown' && rendered?.kind === 'markdown') {
        expect(rendered.markdown).toBe(fixture.content.slice(segment.start as number, segment.end as number));
        expect(rendered.markdown).not.toContain('omnix-ui');
      }
    }
    for (const block of Object.values(fixture.expected.blocks)) {
      expect(chatUiBlockSchema.safeParse(block).success).toBe(true);
    }
    expect(parsed?.text).toBe(fixture.expected.text);
    expect(parsed?.speech).toBe(fixture.expected.speech);
  });

  it('falls back to plain Markdown when an offset is outside the content', () => {
    const fixture = loadFixture('stats_basic');

    expect(parseChatUi({ ui: fixture.expected }, fixture.content.slice(0, 10))).toBeNull();
  });

  it('shows a block that fails client validation as its text', () => {
    const fixture = loadFixture('mixed_reply');
    const ui = structuredClone(fixture.expected) as Fixture['expected'];
    (ui.blocks.headline as Record<string, unknown>).items = [{ label: 'Revenue', value: '$6,930', color: 'red' }];

    const parsed = parseChatUi({ ui }, fixture.content);
    const segment = parsed?.segments.find((item) => item.kind === 'text');
    expect(segment).toEqual({ kind: 'text', key: '1', text: 'Revenue: $6,930 (+4.1%). Orders: 212 (+5.5%).' });
    expect(parsed?.blocks.headline).toBeUndefined();
    expect(parsed?.blocks.b1?.type).toBe('choices');
  });

  it('renders nothing for interrupted, missing or malformed payloads', () => {
    const fixture = loadFixture('stats_basic');

    expect(parseChatUi({ ui: fixture.expected, delivery_status: 'interrupted' }, fixture.content)).toBeNull();
    expect(parseChatUi({}, fixture.content)).toBeNull();
    expect(parseChatUi(undefined, fixture.content)).toBeNull();
    expect(parseChatUi({ ui: { ...fixture.expected, version: 2 } }, fixture.content)).toBeNull();
  });
});

describe('length limits', () => {
  it('counts characters as the server does, so emoji near a limit do not degrade a block', () => {
    const label = '🚀'.repeat(120); // 120 code points, 240 UTF-16 units
    const block = { type: 'stats', id: 'b1', v: 1, items: [{ label, value: '1' }], provenance: 'model', bindings: [] };

    expect(chatUiBlockSchema.safeParse(block).success).toBe(true);
    expect(chatUiBlockSchema.safeParse({ ...block, items: [{ label: `${label}x`, value: '1' }] }).success).toBe(false);
  });
});
