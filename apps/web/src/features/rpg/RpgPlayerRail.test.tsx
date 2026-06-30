import { MantineProvider } from '@mantine/core';
import { fireEvent, render, screen } from '@testing-library/react';
import type { ReactElement } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { omnixTheme } from '../../design/theme';
import { RpgPlayerRail } from './RpgPlayerRail';
import { activeQuests, equippedGear, heroStats as previewHeroStats, partyMembers, previewHeroSummary, previewSurvival } from './rpgUiState';

function renderWithTheme(element: ReactElement) {
  return render(
    <MantineProvider theme={omnixTheme} defaultColorScheme="dark">
      {element}
    </MantineProvider>
  );
}

describe('RpgPlayerRail', () => {
  it('renders hero vitals, equipment, party, quests, and Hermes route decision', () => {
    const onSelectCommand = vi.fn();
    renderWithTheme(
      <RpgPlayerRail
        activeQuests={activeQuests}
        equippedGear={equippedGear}
        heroStats={previewHeroStats}
        heroSummary={previewHeroSummary}
        onSelectCommand={onSelectCommand}
        partyMembers={partyMembers}
        survival={previewSurvival}
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
});
