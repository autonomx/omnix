import { MantineProvider } from '@mantine/core';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, within } from '@testing-library/react';
import type { ReactElement } from 'react';
import { beforeEach, describe, expect, it } from 'vitest';
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
  beforeEach(() => {
    window.localStorage.clear();
  });

  it('replaces runtime status options with a full world lore view', () => {
    renderWithTheme(<RpgWorkspaceHeader {...headerProps} />);

    expect(screen.queryByLabelText('RPG runtime status')).not.toBeInTheDocument();
    expect(screen.queryByText('Replay-preserving')).not.toBeInTheDocument();
    expect(screen.queryByText('/rpg')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'World Lore' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Hide player rail' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Hide world rail' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Expand live data' })).toHaveAttribute('aria-expanded', 'false');

    fireEvent.click(screen.getByRole('button', { name: 'World Lore' }));

    const loreDialog = screen.getByRole('dialog', { name: 'Preview campaign' });
    expect(within(loreDialog).getByRole('heading', { name: 'Preview campaign' })).toBeInTheDocument();
    expect(within(loreDialog).getByText('Select or create a campaign to browse its Campaign Bible.')).toBeInTheDocument();

    fireEvent.click(within(loreDialog).getByRole('button', { name: 'Back to Play' }));
    expect(screen.queryByRole('dialog', { name: 'Preview campaign' })).not.toBeInTheDocument();
  });

  it('opens the world library and keeps bundle import available', async () => {
    const view = renderWithTheme(
      <>
        <section className="rpg-launcher-dialog">
          <div className="rpg-launcher-panel-heading">Campaign Menu</div>
          <div className="rpg-launcher-home-grid" />
        </section>
        <RpgWorkspaceHeader {...headerProps} />
      </>
    );
    const launcherGrid = view.container.querySelector<HTMLElement>('.rpg-launcher-home-grid');
    const launcherDialog = view.container.querySelector<HTMLElement>('.rpg-launcher-dialog');
    expect(launcherGrid).not.toBeNull();
    expect(launcherDialog).not.toBeNull();

    const worldCard = await within(launcherGrid as HTMLElement).findByRole('button', {
      name: /Worlds & Campaigns Create or import worlds/i,
    });
    fireEvent.click(worldCard);

    const worldView = await screen.findByRole('region', { name: 'Worlds and Campaigns view' });
    expect(launcherDialog).toHaveClass('rpg-launcher-dialog-world-library');
    expect(within(worldView).getByRole('heading', { name: 'Worlds' })).toBeInTheDocument();
    expect(within(worldView).getByRole('button', { name: 'Create New World' })).toBeInTheDocument();
    expect(within(worldView).getByText('Export / import world')).toBeInTheDocument();

    fireEvent.click(within(worldView).getByRole('button', { name: 'Back to Play' }));
    expect(screen.queryByRole('region', { name: 'Worlds and Campaigns view' })).not.toBeInTheDocument();
    expect(launcherDialog).not.toHaveClass('rpg-launcher-dialog-world-library');
  });
});
