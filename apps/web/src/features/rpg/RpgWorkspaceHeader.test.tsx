import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
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
  it('renders module context and runtime status anchors', () => {
    renderWithTheme(
      <RpgWorkspaceHeader
        module={{
          id: 'rpg',
          label: 'RPG',
          route: '/rpg',
          summary: 'Run deterministic RPG campaigns.',
        }}
        selectedSessionSummary={previewSessionSummary}
        submitStatus="ready"
      />
    );

    expect(screen.getByRole('heading', { name: 'RPG mode' })).toBeInTheDocument();
    expect(screen.getByText('Run deterministic RPG campaigns.')).toBeInTheDocument();
    expect(screen.getByLabelText('RPG runtime status')).toHaveTextContent('Engine: ready');
    expect(screen.getByLabelText('RPG runtime status')).toHaveTextContent('Session: Preview campaign');
    expect(screen.getByText('Replay-preserving')).toBeInTheDocument();
    expect(screen.getByText('/rpg')).toBeInTheDocument();
  });
});
