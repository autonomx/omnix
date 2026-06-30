import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import type { ReactElement } from 'react';
import { describe, expect, it } from 'vitest';
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

describe('RpgPlayerRail status cards', () => {
  it('shows loading and error states for live rail panels', () => {
    renderWithTheme(
      <RpgPlayerRail
        activeQuests={activeQuests}
        equippedGear={equippedGear}
        heroStats={previewHeroStats}
        heroSummary={previewHeroSummary}
        hermesRouteDecisionState="error"
        hermesTurnReadoutState="loading"
        partyMembers={partyMembers}
        survival={previewSurvival}
      />
    );

    expect(screen.getByRole('region', { name: 'Hermes route decision' })).toHaveTextContent('unavailable');
    expect(screen.getByRole('region', { name: 'Hermes turn readout' })).toHaveTextContent('loading');
  });

  it('shows freshness labels for suggestions and readouts', () => {
    renderWithTheme(
      <RpgPlayerRail
        activeQuests={activeQuests}
        equippedGear={equippedGear}
        heroStats={previewHeroStats}
        heroSummary={previewHeroSummary}
        hermesSuggestionFreshnessLabel="current session"
        hermesSuggestionState="empty"
        hermesTurnReadoutFreshnessLabel="latest turn"
        hermesTurnReadoutState="empty"
        partyMembers={partyMembers}
        survival={previewSurvival}
      />
    );

    expect(screen.getByRole('region', { name: 'Hermes suggested actions' })).toHaveTextContent('current session');
    expect(screen.getByRole('region', { name: 'Hermes turn readout' })).toHaveTextContent('latest turn');
  });
});
