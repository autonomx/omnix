import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import type { ReactElement } from 'react';
import { describe, expect, it } from 'vitest';
import { omnixTheme } from '../../design/theme';
import { RpgStoryScene } from './RpgStoryScene';
import { previewHeroSummary, previewRecentEvents, previewSessionSummary } from './rpgUiState';

function renderWithTheme(element: ReactElement) {
  return render(
    <MantineProvider theme={omnixTheme} defaultColorScheme="dark">
      {element}
    </MantineProvider>
  );
}

describe('RpgStoryScene', () => {
  it('renders scene context, dialogue, recent events, and child controls', () => {
    renderWithTheme(
      <RpgStoryScene
        heroSummary={previewHeroSummary}
        recentEvents={previewRecentEvents}
        selectedSessionSummary={previewSessionSummary}
      >
        <button type="button">Queue RPG turn</button>
      </RpgStoryScene>
    );

    expect(screen.getByRole('region', { name: /Glimmerdeep Pass/ })).toBeInTheDocument();
    expect(screen.getByText('Story / scene')).toBeInTheDocument();
    expect(screen.getByText('Preview campaign')).toBeInTheDocument();
    expect(screen.getByText('Turn 12')).toBeInTheDocument();
    expect(screen.getByLabelText('Glimmerdeep Pass scene preview')).toBeInTheDocument();
    expect(screen.getByText('Alyndra (You)')).toBeInTheDocument();
    expect(screen.getByText('Omnix (Narrator)')).toBeInTheDocument();
    expect(screen.getByText('You arrived at Glimmerdeep Pass.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Queue RPG turn' })).toBeInTheDocument();
  });
});
