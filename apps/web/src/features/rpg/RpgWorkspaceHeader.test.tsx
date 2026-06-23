import { MantineProvider } from '@mantine/core';
import { fireEvent, render, screen } from '@testing-library/react';
import type { ReactElement } from 'react';
import { describe, expect, it } from 'vitest';
import { omnixTheme } from '../../design/theme';
import { RpgWorkspaceHeader } from './RpgWorkspaceHeader';
import { previewSessionSummary } from './rpgUiState';

function renderWithTheme(element: ReactElement) {
  return render(
    <MantineProvider theme={omnixTheme} defaultColorScheme="dark">
      {element}
    </MantineProvider>
  );
}

describe('RpgWorkspaceHeader', () => {
  it('keeps workspace controls available when runtime context is hidden', () => {
    renderWithTheme(
      <RpgWorkspaceHeader
        isLiveDataExpanded={false}
        isPlayerRailCollapsed={false}
        isWorldRailCollapsed={false}
        module={{
          id: 'rpg',
          label: 'RPG',
          route: '/rpg',
          summary: 'Run deterministic RPG campaigns.',
        }}
        onToggleLiveData={() => undefined}
        onTogglePlayerRail={() => undefined}
        onToggleWorldRail={() => undefined}
        selectedSessionSummary={previewSessionSummary}
        submitStatus="ready"
      />
    );

    expect(screen.getByLabelText('RPG runtime status')).toHaveTextContent('Engine: ready');
    expect(screen.getByLabelText('RPG runtime status')).toHaveTextContent('Session: Preview campaign');
    expect(screen.getByText('Replay-preserving')).toBeInTheDocument();
    expect(screen.getByText('/rpg')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Hide player rail' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Hide world rail' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Expand live data' })).toHaveAttribute('aria-expanded', 'false');

    fireEvent.click(screen.getByRole('button', { name: 'Hide header' }));

    expect(screen.queryByLabelText('RPG runtime status')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Show header' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Hide player rail' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Expand live data' })).toBeInTheDocument();
  });
});
