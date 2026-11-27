import { readdirSync, readFileSync, statSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

import { configureViewModules, isApiAllowedForView } from '../../app/viewApiScope';
import { storytellerModule } from './module';

// Every source file of this feature, as text: the API paths its typed client calls.
const here = dirname(fileURLToPath(import.meta.url));

function sources(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return sources(path);
    return /\.tsx?$/u.test(name) && !/\.(?:test|spec)\.tsx?$/u.test(name) && name !== 'generated.ts' ? [path] : [];
  });
}

const CALL = /\bapi\.(?:GET|POST|PUT|PATCH|DELETE)\(\s*'(\/api\/[^']+)'/gu;

describe('storyteller module API scope', () => {
  it('lets the workspace reach every API path its own code calls', () => {
    // A path missing from apiPrefixes is answered in the browser with a 403 that never reaches the gateway:
    // every story-project call failed with "Story request failed with status 403" (/api/story, 2026-11-26).
    configureViewModules([storytellerModule]);
    const called = new Set<string>();
    for (const text of sources(here).map((file) => readFileSync(file, 'utf8'))) {
      for (const match of text.matchAll(CALL)) called.add(match[1]);
    }

    expect(called).toContain('/api/story/projects');
    const blocked = [...called].filter((path) => !isApiAllowedForView(path.replace(/\{[^}]+\}/gu, 'x'), 'storyteller'));
    expect(blocked).toEqual([]);
  });

  it('lets Narrate in Audiobook hand the story over, and nothing else of the audiobook API', () => {
    // The hand-over is called through the audiobook feature's client, which the scan above does not read: it was
    // answered with "The active workspace cannot call this API family" (2026-11-26).
    configureViewModules([storytellerModule]);
    expect(isApiAllowedForView('/api/audiobook/projects/import-story', 'storyteller')).toBe(true);
    expect(isApiAllowedForView('/api/audiobook/projects', 'storyteller')).toBe(false);
    expect(isApiAllowedForView('/api/audiobook/projects/book-one', 'storyteller')).toBe(false);
  });
});
