import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { RpgWorldCampaignCatalog } from './RpgWorldCampaignCatalog';

const world = {
  id: 'world:aurelia',
  title: 'Aurelia: Echoes Beyond the Gate',
  description: 'A reusable fantasy isekai world.',
  status: 'published',
  source_mode: 'imported',
  genre: 'fantasy_isekai',
  tone: 'heroic wonder',
  seed: 482193,
  draft_revision: 1,
  metadata: {},
  scenario_count: 3,
  generation: null,
  created_at: '2026-07-17T00:00:00Z',
  updated_at: '2026-07-17T00:00:00Z',
};

const campaigns = [
  {
    campaign_id: 'campaign:recent',
    title: 'Gateborn Company',
    status: 'active',
    revision: 4,
    updated_at: '2026-07-17T02:00:00Z',
    world_id: world.id,
    world_revision: 1,
    world_release: 1,
    scenario_id: 'scenario:aurelia:first-light',
    scenario_revision: 1,
    binding: {},
  },
  {
    campaign_id: 'campaign:older',
    title: 'Moonroot Expedition',
    status: 'active',
    revision: 2,
    updated_at: '2026-07-17T01:00:00Z',
    world_id: world.id,
    world_revision: 1,
    world_release: 1,
    scenario_id: 'scenario:aurelia:moonroot',
    scenario_revision: 1,
    binding: {},
  },
];

describe('RpgWorldCampaignCatalog', () => {
  it('shows one card per world and supports continuing or creating within that world', () => {
    const onContinueCampaign = vi.fn();
    const onNewCampaign = vi.fn();
    render(
      <RpgWorldCampaignCatalog
        campaigns={campaigns}
        isLoading={false}
        onBack={vi.fn()}
        onContinueCampaign={onContinueCampaign}
        onNewCampaign={onNewCampaign}
        worlds={[world]}
      />,
    );

    expect(screen.getByRole('heading', { name: 'Choose a World' })).toBeInTheDocument();
    expect(screen.getAllByText(world.title).length).toBeGreaterThan(0);
    expect(screen.getByText('3 published openings')).toBeInTheDocument();
    expect(screen.getByText('2 campaigns')).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: `Existing campaigns for ${world.title}` })).toHaveValue('campaign:recent');

    fireEvent.click(screen.getByRole('button', { name: `Continue campaign in ${world.title}` }));
    expect(onContinueCampaign).toHaveBeenCalledWith('campaign:recent');

    fireEvent.change(screen.getByRole('combobox', { name: `Existing campaigns for ${world.title}` }), {
      target: { value: 'campaign:older' },
    });
    fireEvent.click(screen.getByRole('button', { name: `Continue campaign in ${world.title}` }));
    expect(onContinueCampaign).toHaveBeenLastCalledWith('campaign:older');

    fireEvent.click(screen.getByRole('button', { name: `New campaign in ${world.title}` }));
    expect(onNewCampaign).toHaveBeenCalledWith(world.id);
  });

  it('filters cards by title and genre', () => {
    render(
      <RpgWorldCampaignCatalog
        campaigns={[]}
        isLoading={false}
        onBack={vi.fn()}
        onContinueCampaign={vi.fn()}
        onNewCampaign={vi.fn()}
        worlds={[world]}
      />,
    );

    fireEvent.change(screen.getByRole('textbox', { name: 'Search worlds' }), {
      target: { value: 'post apocalyptic' },
    });
    expect(screen.queryByText(world.description)).not.toBeInTheDocument();

    fireEvent.change(screen.getByRole('textbox', { name: 'Search worlds' }), {
      target: { value: 'isekai' },
    });
    expect(screen.getByText(world.description)).toBeInTheDocument();
  });
});
