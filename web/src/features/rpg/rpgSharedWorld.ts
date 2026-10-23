import type { RpgWorldSummary } from './api/rpgWorldLibraryClient';

export interface RpgSharedWorldInfo {
  /** Made in someone else's Omnix and imported here (a download from the catalog, or a bundle file). */
  shared: boolean;
  /** Someone here reviewed and adopted it, so its openings can launch. */
  adopted: boolean;
  bundleSha256: string;
  /** Who shared it, when it came from the community catalog. */
  author: string;
}

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

/** A world's sharing state, from the metadata that import and adoption write. */
export function sharedWorldInfo(world: Pick<RpgWorldSummary, 'metadata'>): RpgSharedWorldInfo {
  const metadata = record(world.metadata);
  const imported = record(metadata.world_bundle_import);
  const bundleSha256 = typeof imported.bundle_sha256 === 'string' ? imported.bundle_sha256 : '';
  const author = record(imported.catalog).author;
  return {
    shared: Boolean(bundleSha256),
    adopted: Object.keys(record(metadata.world_adoption)).length > 0,
    bundleSha256,
    author: typeof author === 'string' ? author : '',
  };
}
