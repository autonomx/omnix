// @vitest-environment node
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const srcRoot = fileURLToPath(new URL('../', import.meta.url));

function stylesheets(folder: string): string[] {
  return readdirSync(folder).flatMap((name) => {
    const path = join(folder, name);
    if (statSync(path).isDirectory()) return stylesheets(path);
    return name.endsWith('.css') ? [path] : [];
  });
}

/** A palette token's lightness, from its name: hue family and OKLab lightness (0-1000), as design/tokens.css names them. */
function lightness(token: string): number {
  return Number(token.split('-')[1]) / 1000;
}

const TOKEN = /var\(--c-([a-z]+-\d+(?:-\d+)?)\)/g;
const FAINT = /color-mix\(in srgb,\s*var\(--c-([a-z]+-\d+(?:-\d+)?)\)\s+([\d.]+)%/g;

/**
 * Colours written for dark mode only: a dark palette colour painted as a background, or a light one used as text,
 * outside a light-mode rule. They stay dark (or light) in light mode; the appearance-aware aliases in
 * design/tokens.css (--bg-, --fg-, --wash-) follow the appearance instead. White text on a coloured button (a
 * mostly opaque mid-lightness background) is allowed.
 */
function darkOnlyColours(css: string): string[] {
  const found: string[] = [];
  const masked = css.replace(/\/\*[\s\S]*?\*\//g, (comment) => comment.replace(/[{}]/g, ' '));
  for (const [, selector, body] of masked.matchAll(/([^{}]*)\{([^{}]*)\}/g)) {
    if (selector.includes('light') || selector.trim().startsWith('@')) continue;
    const declarations = body.split(';').map((item) => item.split(':')).filter((parts) => parts.length > 1)
      .map(([property, ...value]) => [property.trim(), value.join(':')] as const);
    const backgrounds = declarations.filter(([property]) => /^background(-color|-image)?$/.test(property)).map(([, value]) => value);
    const painted = backgrounds.flatMap((value) => [...value.matchAll(TOKEN)].map((match) => match[1]));
    const faint = new Set(backgrounds.flatMap((value) => [...value.matchAll(FAINT)].filter((match) => Number(match[2]) < 60).map((match) => match[1])));
    const accent = painted.some((token) => lightness(token) >= 0.4 && lightness(token) <= 0.72 && !faint.has(token))
      && !painted.some((token) => lightness(token) < 0.4);
    for (const [property, value] of declarations) {
      for (const [, token] of value.matchAll(TOKEN)) {
        if (/^background(-color|-image)?$/.test(property) && lightness(token) < 0.4) found.push(`${selector.trim()} { ${property}: --c-${token} }`);
        if (/^(color|fill|stroke|caret-color)$/.test(property) && lightness(token) > 0.7 && !accent) found.push(`${selector.trim()} { ${property}: --c-${token} }`);
      }
    }
  }
  return found;
}

describe('light and dark appearance', () => {
  it('paints surfaces and text with colours that follow the appearance', () => {
    const offenders = stylesheets(srcRoot)
      .filter((path) => !path.endsWith(join('design', 'tokens.css')))
      .flatMap((path) => darkOnlyColours(readFileSync(path, 'utf8')).map((rule) => `${relative(srcRoot, path)}: ${rule}`));
    expect(offenders).toEqual([]);
  });

  it('finds a dark-only surface and allows white text on a coloured button', () => {
    expect(darkOnlyColours('.panel { background: var(--c-indigo-190); color: var(--c-slate-970-2); }')).toHaveLength(2);
    expect(darkOnlyColours('.panel { background: var(--bg-indigo-190); color: var(--fg-slate-970-2); }')).toEqual([]);
    expect(darkOnlyColours('.send { background: var(--c-indigo-500); color: var(--c-neutral-1000); }')).toEqual([]);
    expect(darkOnlyColours(":root[data-omnix-appearance='light'] .x { background: var(--c-indigo-190); }")).toEqual([]);
  });
});
