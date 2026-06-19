import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { omnixApiClient } from '../../api/client';
import { RpgLoadoutTabs } from './RpgLoadoutTabs';
import { hotbarAbilities, inventoryItems } from './rpgUiState';

type LoadoutTabsProps = Parameters<typeof RpgLoadoutTabs>[0];

function renderLoadoutTabs(props: LoadoutTabsProps) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <RpgLoadoutTabs {...props} />
    </QueryClientProvider>,
  );
}

function mockLiveItemApis() {
  const continueRpgSession = vi.spyOn(omnixApiClient, 'continueRpgSession').mockResolvedValue({ ok: true } as never);
  const applyRpgLoadoutAction = vi.spyOn(omnixApiClient, 'applyRpgLoadoutAction').mockResolvedValue({ ok: true } as never);
  const post = vi.spyOn(omnixApiClient, 'post').mockImplementation(async (_path: `/api/${string}`, body: unknown) => {
    const payload = body as Record<string, unknown>;
    if (payload.action === 'item_objectives') {
      return {
        ok: true,
        objectives: {
          objectives: [
            {
              objective_id: 'craft:torch',
              label: 'Craft torch',
              reason: 'Enough materials are available.',
              action: { action: 'craft', recipe_id: 'torch', station: 'campfire' },
            },
          ],
        },
      } as never;
    }
    if (payload.action === 'item_diagnostics') {
      return {
        ok: true,
        diagnostics: {
          summary: { issue_count: 0, warning_count: 1 },
          report: { summary: { coverage_score: 0.5, detail: '2 of 4 item pillars covered.' } },
          merchant_menu: {
            menu: [
              { id: 'buy:torch', action: 'buy', item_name: 'Torch', description: 'A useful light source.', price: { copper: 4 } },
            ],
          },
        },
      } as never;
    }
    if (payload.action === 'item_maintenance') {
      return { ok: true, maintenance: { summary: { dropped_count: 0 } } } as never;
    }
    return { ok: true } as never;
  });
  return { applyRpgLoadoutAction, continueRpgSession, post };
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
    expect(screen.getByRole('region', { name: 'Item actions and coverage' })).toHaveTextContent('Inventory, crafting, and trade');
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

  it('shows item objectives, status cards, and merchant entries for a live session', async () => {
    mockLiveItemApis();

    renderLoadoutTabs({ hotbarAbilities, inventoryItems, onSelectCommand: vi.fn(), selectedSessionId: 'session-live' });

    expect(await screen.findByText('Craft torch')).toBeInTheDocument();
    expect(screen.getByText('Item diagnostics')).toBeInTheDocument();
    expect(screen.getByText('Item coverage')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'buy Torch' })).toBeInTheDocument();
  });

  it('routes panel item actions through loadout and item command APIs', async () => {
    const { applyRpgLoadoutAction, post } = mockLiveItemApis();

    renderLoadoutTabs({ hotbarAbilities, inventoryItems, onSelectCommand: vi.fn(), selectedSessionId: 'session-live' });
    await screen.findByText('Craft torch');

    fireEvent.click(screen.getByRole('button', { name: 'Use' }));
    await waitFor(() => {
      expect(applyRpgLoadoutAction).toHaveBeenCalledWith('session-live', { action: 'use', item_name: 'Healing potion' });
    });

    post.mockClear();
    fireEvent.click(screen.getByRole('button', { name: 'Sell' }));
    await waitFor(() => {
      expect(post).toHaveBeenCalledWith('/api/rpg/session/get', {
        action: 'item_command',
        session_id: 'session-live',
        command: 'sell Healing potion',
      });
    });
  });

  it('routes structured item objectives through loadout actions', async () => {
    const { applyRpgLoadoutAction } = mockLiveItemApis();

    renderLoadoutTabs({ hotbarAbilities, inventoryItems, onSelectCommand: vi.fn(), selectedSessionId: 'session-live' });

    fireEvent.click(await screen.findByRole('button', { name: 'Craft torch' }));
    await waitFor(() => {
      expect(applyRpgLoadoutAction).toHaveBeenCalledWith('session-live', {
        action: 'craft',
        recipe_id: 'torch',
        station: 'campfire',
      });
    });
  });
});
