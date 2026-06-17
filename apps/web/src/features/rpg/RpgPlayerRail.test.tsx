import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import type { ReactElement } from 'react';
import { describe, expect, it } from 'vitest';
import { omnixTheme } from '../../design/theme';
import { RpgPlayerRail } from './RpgPlayerRail';
import { activeQuests, equippedGear, heroStats as previewHeroStats, partyMembers, previewHeroSummary } from './rpgUiState';

function renderWithTheme(element: ReactElement) {
  return render(
    <MantineProvider theme={omnixTheme} defaultColorScheme="dark">
      {element}
    </MantineProvider>
  );
}

describe('RpgPlayerRail', () => {
  it('renders hero vitals, equipment, party, and quests', () => {
    renderWithTheme(
      <RpgPlayerRail
        activeQuests={activeQuests}
        equippedGear={equippedGear}
        heroStats={previewHeroStats}
        heroSummary={previewHeroSummary}
        partyMembers={partyMembers}
      />
    );

    expect(screen.getByRole('complementary', { name: 'Player, party, and quests' })).toBeInTheDocument();
    expect(screen.getByText('Alyndra')).toBeInTheDocument();
    expect(screen.getByLabelText('HP 86 / 110')).toBeInTheDocument();
    expect(screen.getByLabelText('XP 7,450 / 12,000')).toBeInTheDocument();
    expect(screen.getByText('Longbow of the Boreal Wind')).toBeInTheDocument();
    expect(screen.getByText('Thorin Ironfist')).toBeInTheDocument();
    expect(screen.getByText('3 / 4')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '+ Add companion' })).toBeInTheDocument();
    expect(screen.getByText('The Frostbound Relic')).toBeInTheDocument();
  });
});
