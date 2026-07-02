import { MantineProvider } from '@mantine/core';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ReactElement } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { getHermesRpgApprovedFlowConfig, runHermesRpgApprovedFlow } from '../../api/hermesRpgApprovedFlowClient';
import { omnixTheme } from '../../design/theme';
import { RpgPlayerRail } from './RpgPlayerRail';
import { activeQuests, equippedGear, heroStats as previewHeroStats, partyMembers, previewHeroSummary, previewSurvival } from './rpgUiState';

vi.mock('../../api/hermesRpgApprovedFlowClient', () => ({
  getHermesRpgApprovedFlowConfig: vi.fn(),
  runHermesRpgApprovedFlow: vi.fn(),
}));

function renderWithTheme(element: ReactElement) {
  return render(
    <MantineProvider theme={omnixTheme} defaultColorScheme="dark">
      {element}
    </MantineProvider>
  );
}

const baseRailProps = {
  activeQuests,
  equippedGear,
  heroStats: previewHeroStats,
  heroSummary: previewHeroSummary,
  partyMembers,
  survival: previewSurvival,
};

describe('RpgPlayerRail', () => {
  beforeEach(() => {
    vi.mocked(getHermesRpgApprovedFlowConfig).mockReset();
    vi.mocked(runHermesRpgApprovedFlow).mockReset();
    window.localStorage.clear();
  });

  it('renders hero vitals, equipment, party, quests, and Hermes route decision', () => {
    const onSelectCommand = vi.fn();
    renderWithTheme(
      <RpgPlayerRail
        {...baseRailProps}
        onSelectCommand={onSelectCommand}
      />
    );

    expect(screen.getByRole('complementary', { name: 'Player, party, and quests' })).toBeInTheDocument();
    expect(screen.getByText('Alyndra')).toBeInTheDocument();
    expect(screen.getByLabelText('HP 86 / 110')).toBeInTheDocument();
    expect(screen.getByLabelText('XP 7,450 / 12,000')).toBeInTheDocument();
    expect(screen.getByLabelText('XP 7,450 / 12,000').closest('.rpg-stat-row')).toHaveTextContent('XP7,450 / 12,000');
    expect(screen.getByRole('region', { name: 'Hermes route decision' })).toHaveTextContent('Role');
    expect(screen.getByRole('region', { name: 'Hermes route decision' })).toHaveTextContent('suggest');
    expect(screen.getByRole('region', { name: 'Hermes route decision' })).toHaveTextContent('rpg_sim');
    expect(screen.getByText('Longbow of the Boreal Wind')).toBeInTheDocument();
    expect(screen.getByText('Thorin Ironfist')).toBeInTheDocument();
    expect(screen.getByText('3 / 4')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '+ Add companion' })).toBeInTheDocument();
    expect(screen.getByText('The Frostbound Relic')).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Survival status' })).toHaveTextContent('Hunger24 / 100');
    expect(screen.getByLabelText('Thirst pressure 18 / 100')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Rest' }));
    expect(onSelectCommand).toHaveBeenCalledWith('I rest');
  });

  it('checks approved-flow config before posting a reviewed command', async () => {
    vi.mocked(getHermesRpgApprovedFlowConfig).mockResolvedValue({
      ok: true,
      enabled: false,
      feature_flag: 'HERMES_RPG_APPROVED_FLOW_ENABLED',
    });
    window.localStorage.setItem('omnix:rpg:selected-session-id', 'session-1');

    renderWithTheme(
      <RpgPlayerRail
        {...baseRailProps}
        hermesSuggestionState="ready"
        hermesSuggestions={[{ id: 'look', label: 'Look around', command: 'look around' }]}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: 'Review & apply' }));

    await waitFor(() => {
      expect(screen.getByRole('status')).toHaveTextContent('disabled by config');
    });
    expect(getHermesRpgApprovedFlowConfig).toHaveBeenCalledTimes(1);
    expect(runHermesRpgApprovedFlow).not.toHaveBeenCalled();
  });

  it('posts reviewed commands when config is enabled and refreshes after acceptance', async () => {
    const onApprovedFlowAccepted = vi.fn();
    vi.mocked(getHermesRpgApprovedFlowConfig).mockResolvedValue({ ok: true, enabled: true });
    vi.mocked(runHermesRpgApprovedFlow).mockResolvedValue({ ok: true, state_changed: true });
    window.localStorage.setItem('omnix:rpg:selected-session-id', 'session-1');

    renderWithTheme(
      <RpgPlayerRail
        {...baseRailProps}
        hermesSuggestionState="ready"
        hermesSuggestions={[{ id: 'look', label: 'Look around', command: 'look around' }]}
        onApprovedFlowAccepted={onApprovedFlowAccepted}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: 'Review & apply' }));

    await waitFor(() => {
      expect(runHermesRpgApprovedFlow).toHaveBeenCalledWith({
        enabled: true,
        user_step: { ready: true, command_text: 'look around' },
        replay_entry: { ok: true, command_text: 'look around' },
        context: { session_id: 'session-1', context_hash: 'ui:session-1:look around' },
      });
    });
    await waitFor(() => {
      expect(onApprovedFlowAccepted).toHaveBeenCalledTimes(1);
      expect(screen.getByRole('status')).toHaveTextContent('RPG state is refreshing now');
    });
  });
});
