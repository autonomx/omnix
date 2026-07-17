import { useMemo, useState } from 'react';
import type {
  RpgWorldCampaignSummary,
  RpgWorldSummary,
} from '../../api/rpgWorldLibraryClient';
import './RpgWorldCampaignCatalog.css';

interface RpgWorldCampaignCatalogProps {
  campaigns: RpgWorldCampaignSummary[];
  error?: string;
  isLoading: boolean;
  onBack: () => void;
  onContinueCampaign: (campaignId: string) => void;
  onNewCampaign: (worldId: string) => void;
  worlds: RpgWorldSummary[];
}

function text(value: unknown): string {
  return typeof value === 'string' ? value.trim() : '';
}

function coverImage(world: RpgWorldSummary): string | undefined {
  const metadata = world.metadata ?? {};
  const candidate = [
    metadata.cover_image_url,
    metadata.cover_url,
    metadata.hero_image_url,
    metadata.banner_url,
    metadata.image_url,
  ].map(text).find(Boolean);
  if (!candidate) return undefined;
  return /^(?:https?:\/\/|\/|data:image\/)/i.test(candidate) ? candidate : undefined;
}

function displayGenre(value: string): string {
  return value
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function timestamp(value: string): number {
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function campaignsForWorld(campaigns: RpgWorldCampaignSummary[], worldId: string) {
  return campaigns
    .filter((campaign) => campaign.world_id === worldId && campaign.status !== 'archived')
    .sort((left, right) => timestamp(right.updated_at) - timestamp(left.updated_at));
}

export function RpgWorldCampaignCatalog({
  campaigns,
  error,
  isLoading,
  onBack,
  onContinueCampaign,
  onNewCampaign,
  worlds,
}: RpgWorldCampaignCatalogProps) {
  const [search, setSearch] = useState('');
  const [selectedCampaigns, setSelectedCampaigns] = useState<Record<string, string>>({});
  const visibleWorlds = useMemo(() => {
    const query = search.trim().toLowerCase();
    return worlds
      .filter((world) => world.status !== 'archived')
      .filter((world) => !query || [world.title, world.description, world.genre, world.tone]
        .some((value) => value.toLowerCase().includes(query)))
      .sort((left, right) => timestamp(right.updated_at) - timestamp(left.updated_at));
  }, [search, worlds]);

  return (
    <section className="rpg-world-catalog" aria-label="Available campaign worlds">
      <div className="rpg-world-catalog-heading">
        <div>
          <p className="eyebrow">Reusable worlds</p>
          <h4>Choose a World</h4>
          <p>Select a world to continue one of its campaigns or configure a new campaign from a published opening.</p>
        </div>
        <button className="rpg-secondary-button" type="button" onClick={onBack}>Back</button>
      </div>

      <label className="rpg-world-catalog-search">
        <span>Search worlds</span>
        <input
          aria-label="Search worlds"
          placeholder="Search by title, genre, or tone…"
          value={search}
          onChange={(event) => setSearch(event.currentTarget.value)}
        />
      </label>

      {isLoading ? <p className="rpg-world-catalog-message">Loading reusable worlds…</p> : null}
      {error ? <p className="rpg-world-catalog-error">{error}</p> : null}
      {!isLoading && !error && !visibleWorlds.length ? (
        <p className="rpg-world-catalog-message">
          No reusable worlds match this search. Create or import one from Worlds &amp; Campaigns.
        </p>
      ) : null}

      <div className="rpg-world-card-grid">
        {visibleWorlds.map((world) => {
          const worldCampaigns = campaignsForWorld(campaigns, world.id);
          const selectedCampaignId = selectedCampaigns[world.id] || worldCampaigns[0]?.campaign_id || '';
          const image = coverImage(world);
          const openingCount = world.scenario_count ?? 0;
          return (
            <article className="rpg-world-card" key={world.id}>
              <div
                className={image ? 'rpg-world-card-cover rpg-world-card-cover-image' : 'rpg-world-card-cover'}
                style={image ? { backgroundImage: `linear-gradient(180deg, rgba(3, 7, 18, .04), rgba(3, 7, 18, .88)), url(${JSON.stringify(image)})` } : undefined}
              >
                <span className="rpg-world-card-genre">{displayGenre(world.genre || 'World')}</span>
                <div className="rpg-world-card-cover-copy">
                  <strong>{world.title}</strong>
                  <span>{world.tone || 'Reusable campaign world'}</span>
                </div>
              </div>

              <div className="rpg-world-card-body">
                <div>
                  <h5>{world.title}</h5>
                  <p>{world.description || 'A reusable world ready for campaign play.'}</p>
                </div>
                <div className="rpg-world-card-facts">
                  <span>{openingCount} published opening{openingCount === 1 ? '' : 's'}</span>
                  <span>{worldCampaigns.length} campaign{worldCampaigns.length === 1 ? '' : 's'}</span>
                </div>

                {worldCampaigns.length ? (
                  <label className="rpg-world-card-campaign-select">
                    <span>Existing campaign</span>
                    <select
                      aria-label={`Existing campaigns for ${world.title}`}
                      value={selectedCampaignId}
                      onChange={(event) => setSelectedCampaigns((current) => ({
                        ...current,
                        [world.id]: event.currentTarget.value,
                      }))}
                    >
                      {worldCampaigns.map((campaign) => (
                        <option key={campaign.campaign_id} value={campaign.campaign_id}>
                          {campaign.title} · {campaign.status}
                        </option>
                      ))}
                    </select>
                  </label>
                ) : (
                  <p className="rpg-world-card-empty">No campaigns have started in this world.</p>
                )}

                <div className="rpg-world-card-actions">
                  <button
                    aria-label={`Continue campaign in ${world.title}`}
                    className="rpg-secondary-button"
                    type="button"
                    disabled={!selectedCampaignId}
                    onClick={() => selectedCampaignId && onContinueCampaign(selectedCampaignId)}
                  >
                    Continue
                  </button>
                  <button
                    aria-label={`New campaign in ${world.title}`}
                    className="rpg-primary-button"
                    type="button"
                    disabled={openingCount < 1}
                    onClick={() => onNewCampaign(world.id)}
                  >
                    New Campaign
                  </button>
                </div>
                {openingCount < 1 ? <small>Publish a scenario before creating a campaign.</small> : null}
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}
