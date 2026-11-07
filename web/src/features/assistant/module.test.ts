import { readdirSync, readFileSync, statSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

import { configureViewModules, isApiAllowedForView } from '../../app/viewApiScope';
import { chatbotModule } from './module';

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

describe('chatbot module API scope', () => {
  it('lets the workspace reach every API path its own code calls', () => {
    // The view firewall answers a path missing from apiPrefixes with a 403 made in the browser: the Memory tab showed
    // "Memories could not be loaded" while no request ever reached the gateway (/api/memory-owners, 2026-11-07).
    configureViewModules([chatbotModule]);
    const called = new Set<string>();
    for (const text of sources(here).map((file) => readFileSync(file, 'utf8'))) {
      for (const match of text.matchAll(CALL)) called.add(match[1]);
    }

    expect(called.size).toBeGreaterThan(20);
    expect(called).toContain('/api/memory-owners/{owner_id}');
    const blocked = [...called].filter((path) => !isApiAllowedForView(path.replace(/\{[^}]+\}/gu, 'x'), 'chatbot'));
    expect(blocked).toEqual([]);
  });
});
