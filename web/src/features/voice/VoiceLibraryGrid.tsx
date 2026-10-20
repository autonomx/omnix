import { Button, Text } from '@mantine/core';
import { useMemo, useState } from 'react';
import {
  voiceAssetId,
  voiceAssetMetadata,
  voiceAssetName,
  voiceInitial,
  voiceLanguage,
  voiceProfileName,
  voiceSource,
  type VoiceAsset,
} from './voiceAssets';
import './VoiceStudioWorkspace.css';

type SourceFilter = 'all' | 'cloned' | 'designed' | 'preset';
const FAVOURITES_KEY = 'omnix.voice.favourites';

function loadFavourites(): Set<string> {
  try {
    const raw = window.localStorage.getItem(FAVOURITES_KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    return new Set(Array.isArray(parsed) ? parsed.filter((entry): entry is string => typeof entry === 'string') : []);
  } catch {
    return new Set();
  }
}

/** The voice library as cards: preview, language, where the voice came from, favourite. */
export function VoiceLibraryGrid({
  assets,
  loading,
  failed,
  refreshing,
  onRefresh,
  onPreview,
  onUse,
  onDelete,
  deletingId,
  deleteFailed,
}: {
  assets: VoiceAsset[];
  loading: boolean;
  failed: boolean;
  refreshing: boolean;
  onRefresh: () => void;
  /** Preview and Use need Voice Studio's engine and script; other hosts leave them out. */
  onPreview?: (asset: VoiceAsset) => void;
  onUse?: (asset: VoiceAsset) => void;
  onDelete: (asset: VoiceAsset) => void;
  deletingId: string;
  deleteFailed: boolean;
}) {
  const [search, setSearch] = useState('');
  const [source, setSource] = useState<SourceFilter>('all');
  const [favourites, setFavourites] = useState<Set<string>>(loadFavourites);
  const [favouritesOnly, setFavouritesOnly] = useState(false);
  const shown = useMemo(() => {
    const query = search.trim().toLowerCase();
    return assets
      .filter((asset) => !query || voiceAssetName(asset).toLowerCase().includes(query) || voiceProfileName(asset).toLowerCase().includes(query))
      .filter((asset) => source === 'all' || voiceSource(asset) === source)
      .filter((asset) => !favouritesOnly || favourites.has(voiceAssetId(asset)))
      .sort((left, right) => Number(favourites.has(voiceAssetId(right))) - Number(favourites.has(voiceAssetId(left))));
  }, [assets, favourites, favouritesOnly, search, source]);

  function toggleFavourite(asset: VoiceAsset) {
    setFavourites((current) => {
      const next = new Set(current);
      const id = voiceAssetId(asset);
      if (next.has(id)) next.delete(id); else next.add(id);
      try {
        window.localStorage.setItem(FAVOURITES_KEY, JSON.stringify([...next]));
      } catch {
        // Favourites are a per-browser convenience; blocked storage just forgets them.
      }
      return next;
    });
  }

  return (
    <section className="voice-library" aria-label="Voice Library">
      <div className="voice-section-head">
        <div><h3>Voice Library</h3><Text size="sm">Voices you can cast in Speak.</Text></div>
        <Button aria-label="Refresh voice library" size="xs" variant="subtle" loading={refreshing} onClick={onRefresh}>Refresh ⟳</Button>
      </div>
      <div className="voice-library-filters">
        <label className="voice-search"><span>Search voices</span><input aria-label="Search voices" value={search} onChange={(event) => setSearch(event.currentTarget.value)} placeholder="Search voices..." /></label>
        <label className="voice-search"><span>Source</span><select aria-label="Voice source" value={source} onChange={(event) => setSource(event.currentTarget.value as SourceFilter)}><option value="all">All</option><option value="cloned">Cloned</option><option value="designed">Designed</option><option value="preset">Preset</option></select></label>
        <label className="voice-favourites-only"><input type="checkbox" checked={favouritesOnly} onChange={(event) => setFavouritesOnly(event.currentTarget.checked)} />Favourites</label>
      </div>
      {loading ? <div className="platform-empty" role="status">Loading voices…</div> : failed ? (
        <div className="platform-empty" role="alert">Voice Library failed to load. The local asset index may be unavailable.<Button aria-label="Retry voice library" size="xs" variant="subtle" onClick={onRefresh}>Retry</Button></div>
      ) : shown.length ? (
        <div className="voice-card-grid" role="list" aria-label="Voices">
          {shown.map((asset) => {
            const id = voiceAssetId(asset);
            const favourite = favourites.has(id);
            const check = voiceAssetMetadata(asset).sample_check as { warnings?: unknown } | undefined;
            const warnings = Array.isArray(check?.warnings) ? check.warnings.length : 0;
            return (
              <article className="voice-card" role="listitem" key={id}>
                <div className="voice-card-top">
                  <i aria-hidden="true">{voiceInitial(asset)}</i>
                  <div><b>{voiceAssetName(asset)}</b><small title={voiceProfileName(asset)}>{voiceProfileName(asset)}</small></div>
                  <button type="button" className="voice-favourite" aria-pressed={favourite} aria-label={`${favourite ? 'Unfavourite' : 'Favourite'} ${voiceAssetName(asset)}`} onClick={() => toggleFavourite(asset)}>{favourite ? '★' : '☆'}</button>
                </div>
                <div className="voice-card-tags">
                  <span className="ready-chip">{voiceSource(asset)}</span>
                  {voiceLanguage(asset) ? <span className="voice-tag">{voiceLanguage(asset)}</span> : null}
                  {warnings ? <span className="voice-tag voice-tag-warn" title="The sample check reported issues when this voice was cloned.">sample check: {warnings}</span> : null}
                </div>
                <div className="voice-library-actions">
                  {onPreview ? <Button aria-label={`Preview ${voiceAssetName(asset)}`} size="xs" variant="subtle" onClick={() => onPreview(asset)}>Preview</Button> : null}
                  {onUse ? <Button size="xs" variant="subtle" onClick={() => onUse(asset)}>Use</Button> : null}
                  <Button aria-label={`Delete ${voiceAssetName(asset)}`} color="red" loading={deletingId === id} size="xs" variant="outline" onClick={() => onDelete(asset)}>Delete</Button>
                </div>
              </article>
            );
          })}
        </div>
      ) : <div className="platform-empty" role="status">{assets.length ? 'No voices match these filters.' : 'No cloned voices were indexed. Create a clone or refresh the library to rescan local voice files.'}</div>}
      {deleteFailed ? <div className="platform-empty" role="alert">Voice deletion failed. The voice was not removed.</div> : null}
      <Text size="xs">{shown.length} of {assets.length} voices</Text>
    </section>
  );
}
