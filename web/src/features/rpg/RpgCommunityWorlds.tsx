import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { catalogCoverUrl, rpgWorldSharingClient, type RpgWorldCatalogEntry } from './api/rpgWorldSharingClient';
import { RpgWorldCard } from './RpgWorldCard';

interface RpgCommunityWorldsProps {
  /** A downloaded world waiting to be reviewed and adopted. */
  onReview: (worldId: string) => void;
  onPlay: (worldId: string) => void;
}

function megabytes(bytes: number): string {
  return `${Math.max(0.1, bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function CommunityWorldActions({ entry, installing, onInstall, onPlay, onReview }: {
  entry: RpgWorldCatalogEntry;
  installing: boolean;
  onInstall: () => void;
  onPlay: (worldId: string) => void;
  onReview: (worldId: string) => void;
}) {
  const installed = entry.installed;
  if (installed && installed.version >= entry.version) {
    return installed.adopted
      ? <button type="button" onClick={() => onPlay(installed.world_id)}>Play</button>
      : <button type="button" onClick={() => onReview(installed.world_id)}>Review &amp; adopt</button>;
  }
  return (
    <button disabled={installing} type="button" onClick={onInstall}>
      {installing ? 'Downloading…' : installed ? `Download version ${entry.version}` : 'Download'}
    </button>
  );
}

/** Worlds people have shared on GitHub: download one, then review and adopt it before playing. */
export function RpgCommunityWorlds({ onReview, onPlay }: RpgCommunityWorldsProps) {
  const queryClient = useQueryClient();
  const catalog = useQuery({
    queryKey: ['feature', 'rpg', 'world-catalog'],
    queryFn: () => rpgWorldSharingClient.catalog(),
    staleTime: 60_000,
  });
  const install = useMutation({
    mutationFn: (entryId: string) => rpgWorldSharingClient.install(entryId),
    onSuccess: async (result) => {
      await queryClient.invalidateQueries({ queryKey: ['feature', 'rpg'] });
      if (result.adopted) onPlay(result.world_id);
      else onReview(result.world_id);
    },
  });
  const repo = catalog.data?.repo ?? 'autonomx/omnix-worlds';
  return (
    <section className="rpg-community-worlds" aria-label="Community worlds">
      <p className="rpg-community-intro">
        Worlds people have shared on GitHub, in <a href={`https://github.com/${repo}`} rel="noreferrer" target="_blank">{repo}</a>.
        A download joins My worlds; you review and adopt it before playing. To share one of yours, open its More menu.
      </p>
      {catalog.isPending ? <p>Loading community worlds…</p> : null}
      {catalog.isError ? <p className="rpg-world-catalog-error" role="alert">Couldn&apos;t reach the community catalog. {catalog.error instanceof Error ? catalog.error.message : ''}</p> : null}
      {install.isError ? <p className="rpg-authoring-feedback" role="alert">{install.error instanceof Error ? install.error.message : 'The world could not be downloaded.'}</p> : null}
      {catalog.data && !catalog.data.worlds.length ? <p>No worlds have been shared yet. Be the first: open one of your worlds&apos; More menu and choose Share to community.</p> : null}
      <div className="rpg-world-card-grid">
        {(catalog.data?.worlds ?? []).map((entry) => (
          <RpgWorldCard
            key={entry.id}
            world={{
              id: entry.id,
              title: entry.title,
              description: entry.summary,
              genre: entry.genre,
              tone: entry.tone,
              metadata: entry.has_cover ? { cover_image_url: catalogCoverUrl(entry.id) } : {},
            }}
            facts={<><span>by @{entry.author}</span><span>Version {entry.version}</span><span>{megabytes(Number(entry.bundle.bytes) || 0)}</span></>}
            actions={(
              <CommunityWorldActions
                entry={entry}
                installing={install.isPending && install.variables === entry.id}
                onInstall={() => install.mutate(entry.id)}
                onPlay={onPlay}
                onReview={onReview}
              />
            )}
          />
        ))}
      </div>
    </section>
  );
}
