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
  it('hides by default and restores collapsed runtime context on request', () => {
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

    expect(screen.getByRole('button', { name: 'Show RPG headers' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'RPG mode' })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Show RPG headers' }));

    expect(screen.getByRole('heading', { name: 'RPG mode' })).toBeInTheDocument();
    expect(screen.getByText('Run deterministic RPG campaigns.')).not.toBeVisible();
    expect(screen.getByLabelText('RPG runtime status')).toHaveTextContent('Engine: ready');
    expect(screen.getByLabelText('RPG runtime status')).toHaveTextContent('Session: Preview campaign');
    expect(screen.getByText('Replay-preserving')).toBeInTheDocument();
    expect(screen.getByText('/rpg')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Expand header' })).toHaveAttribute('aria-expanded', 'false');

    fireEvent.click(screen.getByRole('button', { name: 'Expand header' }));

    expect(screen.getByText('Run deterministic RPG campaigns.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Collapse header' })).toHaveAttribute('aria-expanded', 'true');
  });
});
