import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { RpgLiveDataStatus } from './RpgLiveDataStatus';

describe('RpgLiveDataStatus', () => {
  it('summarizes loading, empty, error, and ready source states', () => {
    render(
      <RpgLiveDataStatus
        cards={[
          { id: 'sessions', label: 'Sessions', state: 'loading', detail: 'Loading replay persistence inventory.' },
          { id: 'jobs', label: 'Jobs', state: 'error', detail: 'Job source failed.' },
          { id: 'checkpoints', label: 'Checkpoints', state: 'empty', detail: 'No checkpoint artifacts.' },
          { id: 'reports', label: 'Reports', state: 'ready', detail: '1 report ready.' },
        ]}
      />,
    );

    expect(screen.getByRole('region', { name: 'RPG live data status' })).toBeInTheDocument();
    expect(screen.getByText('1 source need attention')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Expand live data' })).toHaveAttribute('aria-expanded', 'false');
    expect(screen.getByLabelText('Sessions status')).not.toBeVisible();

    fireEvent.click(screen.getByRole('button', { name: 'Expand live data' }));

    expect(screen.getByRole('button', { name: 'Collapse live data' })).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByLabelText('Sessions status')).toHaveTextContent('Loading');
    expect(screen.getByLabelText('Jobs status')).toHaveTextContent('Error');
    expect(screen.getByLabelText('Checkpoints status')).toHaveTextContent('Empty');
    expect(screen.getByLabelText('Reports status')).toHaveTextContent('Ready');
  });

  it('reports ready status when every live source is available', () => {
    render(
      <RpgLiveDataStatus
        cards={[
          { id: 'sessions', label: 'Sessions', state: 'ready', detail: '1 session available.' },
          { id: 'jobs', label: 'Jobs', state: 'ready', detail: '1 job visible.' },
        ]}
      />,
    );

    expect(screen.getByText('All live sources ready')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Expand live data' })).toBeInTheDocument();
  });
});
