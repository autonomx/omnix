import { QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { rpgItemGatewayClient } from './rpgItemApi';
import { rpgSessionClient } from './api/rpgSessionClient';
import { RpgLoadoutTabs } from './RpgLoadoutTabs';
import { hotbarAbilities, inventoryItems } from './rpgUiPreview';
import { createTestQueryClient } from '../../test/renderWithProviders';

type LoadoutTabsProps = Parameters<typeof RpgLoadoutTabs>[0];

function renderLoadoutTabs(props: LoadoutTabsProps) {
  const queryClient = createTestQueryClient();

  return render(
    <QueryClientProvider client={queryClient}>
      <RpgLoadoutTabs {...props} />
    </QueryClientProvider>,
  );
}

function mockLiveItemApis(sessionPayload: Record<string, unknown> = { ok: true }) {
  const getRpgSession = vi.spyOn(rpgSessionClient, 'getRpgSession').mockResolvedValue(sessionPayload as never);
  const post = vi.spyOn(rpgItemGatewayClient, 'post').mockImplementation(async (_path: `/api/${string}`, body: unknown) => {
    const payload = body as Record<string, unknown>;
    if (payload.action === 'ability_detail') {
      return {
        ok: true,
        ability_detail: {
          ability_id: payload.ability_id,
          name: payload.ability_name,
          summary: `LLM ability detail: ${payload.ability_name} is grounded in the current campaign.`,
          resource_cost: { stamina: 10 },
          cooldown_turns: 1,
          source: 'llm',
        },
      } as never;
    }
    return { ok: true } as never;
  });
  return { getRpgSession, post };
}

function liveAbilitySession() {
  return {
    ok: true,
    session: {
      state: {
        player: { level: 2, skills: { stealth: { level: 1, xp: 10, xp_to_next: 50 } } },
        skill_progression: {
          swordsmanship: { rank: 2, xp: 35, last_source: 'training' },
        },
        ability_tree: {
          tree_id: 'warden-tree',
          class_name: 'Warden',
          categories: [
            { category_id: 'traits', name: 'Traits', capability: 'resolve', dimensions: ['relationships'], abilities: ['steady_hand'] },
          ],
          abilities: [
            {
              ability_id: 'steady_hand',
              name: 'Steady Hand',
              kind: 'narrative_trait',
              purpose: 'support',
              dimensions: ['relationships'],
              influence_tags: ['calm'],
              icon: '◇',
              description: 'Keeps the party steady under pressure.',
            },
          ],
        },
        ability_state: {
          unlocked: ['steady_hand'],
          ranks: { steady_hand: 1 },
          active_effects: [{ name: 'Calm Focus', purpose: 'steady aim', dimensions: ['resources'], remaining_turns: 2 }],
        },
        mechanics: {
          ability_coverage_latest: {
            ok: false,
            coverage_score: 0.25,
            total_observations: 3,
            covered_dimensions: ['relationships'],
            missing_dimensions: ['resources'],
            dimension_counts: { relationships: 3 },
            source_counts: { trait: 3 },
            warnings: ['resources missing'],
          },
        },
      },
    },
  };
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('RpgLoadoutTabs', () => {
  it('renders inventory by default and switches to abilities and hotbar panels', () => {
    renderLoadoutTabs({ hotbarAbilities, inventoryItems, onSelectCommand: vi.fn() });

    expect(screen.getByRole('tab', { name: 'Inventory' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tabpanel', { name: 'Inventory' })).toHaveTextContent('12');
    expect(screen.getByRole('button', { name: 'Healing potion' })).toBeInTheDocument();
    expect(screen.getByLabelText('Selected item details: Healing potion')).toHaveTextContent('Nothing more is known of it.');
    expect(screen.getByRole('region', { name: 'Selected item' })).toHaveTextContent('Item details and actions');
    expect(screen.getByRole('button', { name: 'Use' })).toBeDisabled();

    fireEvent.click(screen.getByRole('tab', { name: 'Abilities' }));

    expect(screen.getByRole('tab', { name: 'Abilities' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tabpanel', { name: 'Abilities' })).toHaveTextContent('Aimed Shot');
    expect(screen.getByRole('complementary', { name: 'Active ability: Aimed Shot' })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('tab', { name: 'Hotbar' }));

    expect(screen.getByRole('tab', { name: 'Hotbar' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tabpanel', { name: 'Hotbar' })).toHaveTextContent('Frost Arrow');
    expect(screen.getByRole('button', { name: /Aimed Shot/ })).toBeInTheDocument();
  });

  it('turns ability interactions into replay-preserving commands without a live session', () => {
    const onSelectCommand = vi.fn();
    renderLoadoutTabs({ hotbarAbilities, inventoryItems, onSelectCommand });

    fireEvent.click(screen.getByRole('tab', { name: 'Abilities' }));
    const activeAbility = screen.getByRole('complementary', { name: 'Active ability: Aimed Shot' });
    fireEvent.click(within(activeAbility).getByRole('button', { name: 'Use' }));

    expect(onSelectCommand).toHaveBeenLastCalledWith('Use Aimed Shot on the most relevant target.');

    fireEvent.click(screen.getByRole('tab', { name: 'Hotbar' }));
    fireEvent.click(screen.getByRole('button', { name: /Frost Arrow/ }));

    expect(onSelectCommand).toHaveBeenLastCalledWith('Use Frost Arrow from hotbar slot 2 on the best available target.');
  });

  it('wires the empty inventory slot to a pickup/search command', () => {
    const onSelectCommand = vi.fn();
    renderLoadoutTabs({ hotbarAbilities, inventoryItems, onSelectCommand });

    fireEvent.click(screen.getByRole('button', { name: 'Search for inventory supplies' }));

    expect(onSelectCommand).toHaveBeenLastCalledWith('Search the area for useful supplies I can pick up and add to my inventory.');
  });

  it('shows the item as the world describes it, with only the actions the game offers', () => {
    const cloak = { icon: '◇', count: '1', label: 'Travel Cloak', actions: ['unequip', 'drop', 'sell'], category: 'clothing', description: 'keeps the rain off', worn: true };
    renderLoadoutTabs({ hotbarAbilities, inventoryItems: [cloak], onSelectCommand: vi.fn(), selectedSessionId: 'session-live' });

    const details = screen.getByLabelText('Selected item details: Travel Cloak');
    expect(details).toHaveTextContent('Keeps the rain off.');
    expect(details).toHaveTextContent('StatusWorn');
    const toolbar = screen.getByRole('toolbar', { name: 'Selected item contextual actions' });
    expect(within(toolbar).getAllByRole('button').map((button) => button.getAttribute('aria-label'))).toEqual(['Unequip', 'Drop', 'Sell']);
  });

  it('takes each pack action as a turn: the loadout one, or a typed sale', () => {
    const onApplyLoadoutAction = vi.fn();
    const onSubmitCommand = vi.fn();
    const potion = { icon: '◇', count: '2', label: 'Healing Potion', actions: ['use', 'drop', 'sell'] };
    renderLoadoutTabs({ hotbarAbilities, inventoryItems: [potion], onApplyLoadoutAction, onSelectCommand: vi.fn(), onSubmitCommand, selectedSessionId: 'session-live' });

    fireEvent.click(screen.getByRole('button', { name: 'Use' }));
    expect(onApplyLoadoutAction).toHaveBeenCalledWith({ action: 'use', item_name: 'Healing Potion' });
    fireEvent.click(screen.getByRole('button', { name: 'Sell' }));
    expect(onSubmitCommand).toHaveBeenCalledWith('I sell the Healing Potion.');
  });

  it('describes an ability on hover from its own detail', async () => {
    mockLiveItemApis();
    renderLoadoutTabs({ hotbarAbilities, inventoryItems, onSelectCommand: vi.fn(), selectedSessionId: 'session-live' });

    fireEvent.mouseEnter(screen.getByRole('button', { name: 'Aimed Shot' }));
    const abilityDescription = await screen.findByText('LLM ability detail: Aimed Shot is grounded in the current campaign.');
    const abilityTooltip = abilityDescription.closest('[role="tooltip"]');
    expect(abilityTooltip).toHaveTextContent('10 Stamina');
    expect(abilityTooltip).toHaveTextContent('1-turn cooldown');
  });

  it('wires skills, traits, effects, and coverage panels to commands or live refresh', async () => {
    const onSelectCommand = vi.fn();
    const { getRpgSession } = mockLiveItemApis(liveAbilitySession());

    renderLoadoutTabs({ hotbarAbilities, inventoryItems, onSelectCommand, selectedSessionId: 'session-live' });

    fireEvent.click(screen.getByRole('tab', { name: 'Skills' }));
    expect(await screen.findByText('Swordsmanship')).toBeInTheDocument();
    // The character sheet's skills show too, measured against their own next level.
    expect(screen.getByText('Stealth')).toBeInTheDocument();
    expect(screen.getByRole('progressbar', { name: 'Stealth progress to rank 2' })).toHaveAttribute('aria-valuemax', '50');
    fireEvent.click(screen.getByRole('button', { name: 'Practice Swordsmanship' }));
    expect(onSelectCommand).toHaveBeenLastCalledWith('Practice Swordsmanship with a careful training drill and record any skill progress.');

    fireEvent.click(screen.getByRole('tab', { name: 'Traits' }));
    expect(await screen.findByText('Steady Hand')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Use trait' }));
    expect(onSelectCommand).toHaveBeenLastCalledWith('Lean on the Steady Hand trait to influence my next action.');

    fireEvent.click(screen.getByRole('tab', { name: 'Effects' }));
    expect(await screen.findByText('Calm Focus')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Use effect' }));
    expect(onSelectCommand).toHaveBeenLastCalledWith('Act while taking advantage of the active effect Calm Focus.');

    fireEvent.click(screen.getByRole('tab', { name: 'Coverage' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Practice missing dimension' }));
    expect(onSelectCommand).toHaveBeenLastCalledWith('Practice or use an ability that covers the Resources dimension.');

    const previousRefreshCalls = getRpgSession.mock.calls.length;
    fireEvent.click(screen.getByRole('button', { name: 'Refresh coverage' }));
    await waitFor(() => {
      expect(getRpgSession.mock.calls.length).toBeGreaterThan(previousRefreshCalls);
    });
  });
});
