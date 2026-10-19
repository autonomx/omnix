import { readdirSync, readFileSync, statSync } from 'node:fs';
import { dirname, join, relative, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

// GUI-4.2: chat's generative UI is read-only by construction. It reaches trading only through
// the read-only bars helper, which calls the chart's bars endpoint and nothing else.
const here = dirname(fileURLToPath(import.meta.url));
const featuresRoot = resolve(here, '../../..');
const tradingHelper = join(featuresRoot, 'trading', 'chatPriceBars.ts');

function sources(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return sources(path);
    return /\.(ts|tsx)$/.test(name) && !/\.test\.tsx?$/.test(name) ? [path] : [];
  });
}

function imports(file: string): Array<{ names: string; target: string }> {
  const text = readFileSync(file, 'utf8');
  return [...text.matchAll(/import\s+(type\s+)?([^'"]*?)\s*from\s*['"]([^'"]+)['"]/g), ...text.matchAll(/import\(\s*['"]([^'"]+)['"]\s*\)/g)]
    .map((match) => match.length > 3
      ? { names: match[2], target: relative(featuresRoot, resolve(dirname(file), match[3])) }
      : { names: '', target: relative(featuresRoot, resolve(dirname(file), match[1])) });
}

const WRITE_PATH = /\/api\/trading\/(?:paper|orders?|alerts?|watchlists?|strategies|strategy|drawings|workspaces|scripts|broker)/i;

describe('generative UI import boundary', () => {
  it('imports trading only through its index, and only the read-only bars helper', () => {
    for (const file of sources(here)) {
      for (const { names, target } of imports(file)) {
        if (!target.startsWith(`trading${sep}`) && target !== 'trading') continue;
        expect(target, file).toBe('trading');
        const imported = names.replace(/[{}]/g, '').split(',').map((name) => name.trim().replace(/^type\s+/, '')).filter(Boolean);
        for (const name of imported) expect(['fetchChatPriceBars', 'tradingChartHref', 'ChatPriceBar'], `${file}: ${name}`).toContain(name);
      }
    }
  });

  it('never names a trading write path or another feature’s internals', () => {
    for (const file of sources(here)) {
      const text = readFileSync(file, 'utf8');
      expect(text, file).not.toMatch(WRITE_PATH);
      expect(text, file).not.toMatch(/\.(?:POST|PUT|PATCH|DELETE)\(\s*['"]\/api\/trading/);
    }
  });

  it('keeps the trading helper to one GET of the bars endpoint', () => {
    const text = readFileSync(tradingHelper, 'utf8');
    const calls = [...text.matchAll(/api\.(GET|POST|PUT|PATCH|DELETE)\(\s*['"]([^'"]+)['"]/g)].map((match) => `${match[1]} ${match[2]}`);

    expect(calls).toEqual(['GET /api/trading/bars']);
    expect(imports(tradingHelper).map((entry) => entry.target).sort()).toEqual([join('..', 'api', 'http'), join('trading', 'api', 'gateway')].sort());
  });
});
