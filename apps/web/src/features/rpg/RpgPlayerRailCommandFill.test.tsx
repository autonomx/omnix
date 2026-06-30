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

describe('RpgPlayerRail command fill', () => {
  it('calls the command callback once when a prepared action is used', () => {
    const onSelectCommand = vi.fn();
    renderWithTheme(
      <RpgPlayerRail
        activeQuests={activeQuests}
        equippedGear={equippedGear}
        heroStats={previewHeroStats}
        heroSummary={previewHeroSummary}
        hermesSuggestionState="ready"
        hermesSuggestions={[{ id: 'one', label: 'Ask', command: 'ask at the tavern' }]}
        onSelectCommand={onSelectCommand}
        partyMembers={partyMembers}
        survival={previewSurvival}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: 'Use' }));

    expect(onSelectCommand).toHaveBeenCalledTimes(1);
    expect(onSelectCommand).toHaveBeenCalledWith('ask at the tavern');
  });
});
