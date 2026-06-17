import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import type { ReactElement } from 'react';
import { describe, expect, it } from 'vitest';
import { omnixTheme } from '../../design/theme';
import { RpgWorldRail } from './RpgWorldRail';
import {
  npcRelationships,
  previewEncounter,
  previewJobs,
  previewSessionSummary,
  previewWorldStateRows,
} from './rpgUiState';

function renderWithTheme(element: ReactElement) {
  return render(
    <MantineProvider theme={omnixTheme} defaultColorScheme="dark">
      {element}
    </MantineProvider>
  );
}

describe('RpgWorldRail', () => {
  it('renders world state, encounter, relationships, jobs, and reports', () => {
    renderWithTheme(
      <RpgWorldRail
        checkpointSummary={{ label: 'Latest checkpoint', detail: 'checkpoint-001.json', source: 'live' }}
        encounter={previewEncounter}
        jobCards={previewJobs}
        npcRelationships={npcRelationships}
        rpgAssets={[{ id: 'asset-1', module: 'rpg', storage_path: 'sessions/checkpoint-001.json', type: 'rpg_checkpoint' }]}
        rpgJobCount={0}
        rpgReportCount={2}
        selectedSessionSummary={previewSessionSummary}
        worldStateRows={previewWorldStateRows}
      />
    );

    expect(screen.getByRole('complementary', { name: 'World, jobs, and reports' })).toBeInTheDocument();
    expect(screen.getByLabelText('Glimmerdeep Pass travel map')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Change location' })).toBeInTheDocument();
    expect(screen.getByText('World state')).toBeInTheDocument();
    expect(screen.getByText('Day 18 • 09:42')).toBeInTheDocument();
    expect(screen.getByLabelText('No active combat encounter state')).toBeInTheDocument();
    expect(screen.getByText('Preview encounter state')).toBeInTheDocument();
    expect(screen.getByText('Thorin Ironfist')).toBeInTheDocument();
    expect(screen.getByText('RPG jobs')).toBeInTheDocument();
    expect(screen.getByText('Preview')).toBeInTheDocument();
    expect(screen.getByLabelText('rpg.turn progress')).toBeInTheDocument();
    expect(screen.getByText('2 ready')).toBeInTheDocument();
    expect(screen.getByText('Latest checkpoint: checkpoint-001.json')).toBeInTheDocument();
    expect(screen.getByText('rpg_checkpoint / rpg')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Create checkpoint' })).toBeInTheDocument();
  });
});
