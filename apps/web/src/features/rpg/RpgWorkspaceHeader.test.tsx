import { MantineProvider } from '@mantine/core';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, within } from '@testing-library/react';
import type { ReactElement } from 'react';
import { describe, expect, it, vi } from 'vitest';
import type { OmnixModuleDefinition } from '../../app/modules';
import { omnixTheme } from '../../design/theme';
import { RpgWorkspaceHeader } from './RpgWorkspaceHeader';
import { previewSessionSummary } from './rpgUiState';

function renderWithTheme(element: ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <MantineProvider theme={omnixTheme} defaultColorScheme="dark">
        {element}
      </MantineProvider>
    </QueryClientProvider>
  );
}

const rpgModule: OmnixModuleDefinition = {
  id: 'rpg',
  label: 'RPG',
  route: '/rpg',
  summary: 'Run deterministic RPG campaigns.',
};

const headerProps = {
  isLiveDataExpanded: false,
  isPlayerRailCollapsed: false,
  isWorldRailCollapsed: false,
  module: rpgModule,
  onToggleLiveData: () => undefined,
  onTogglePlayerRail: () => undefined,
  onToggleWorldRail: () => undefined,
  selectedSessionSummary: previewSessionSummary,
  submitStatus: 'ready',
};

describe('RpgWorkspaceHeader', () => {
  it('keeps workspace controls available when runtime context is hidden', () => {
    renderWithTheme(<RpgWorkspaceHeader {...headerProps} />);

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

  it('adds world creation and import to the Campaign Menu', async () => {
    const closeLauncher = vi.fn();
    const view = renderWithTheme(
      <>
        <div className="rpg-launcher-home-grid" />
        <button className="rpg-launcher-backdrop" type="button" onClick={closeLauncher}>Close launcher</button>
        <RpgWorkspaceHeader {...headerProps} />
      </>
    );
    const launcherGrid = view.container.querySelector<HTMLElement>('.rpg-launcher-home-grid');
    expect(launcherGrid).not.toBeNull();

    const worldCard = await within(launcherGrid as HTMLElement).findByRole('button', {
      name: /Worlds & Campaigns Create or import worlds/i,
    });
    fireEvent.click(worldCard);

    expect(closeLauncher).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('dialog', { name: 'Worlds and Campaigns' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Worlds & Campaigns' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Create world' })).toBeInTheDocument();
    expect(screen.getByText('Export / import world')).toBeInTheDocument();
  });
});
