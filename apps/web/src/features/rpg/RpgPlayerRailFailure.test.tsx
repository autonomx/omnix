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

describe('RpgPlayerRail failure states', () => {
  it('keeps RPG command actions usable when Hermes panels fail', () => {
    const onSelectCommand = vi.fn();
    renderWithTheme(
      <RpgPlayerRail
        activeQuests={activeQuests}
        equippedGear={equippedGear}
        heroStats={previewHeroStats}
        heroSummary={previewHeroSummary}
        hermesRouteDecisionState="error"
        hermesSuggestionState="error"
        hermesTurnReadoutState="error"
        onSelectCommand={onSelectCommand}
        partyMembers={partyMembers}
        survival={previewSurvival}
      />
    );

    expect(screen.getByRole('region', { name: 'Hermes route decision' })).toHaveTextContent('unavailable');
    expect(screen.getByRole('region', { name: 'Hermes suggested actions' })).toHaveTextContent('unavailable');
    expect(screen.getByRole('region', { name: 'Hermes turn readout' })).toHaveTextContent('unavailable');

    fireEvent.click(screen.getByRole('button', { name: 'Rest' }));

    expect(onSelectCommand).toHaveBeenCalledWith('I rest');
  });
});
