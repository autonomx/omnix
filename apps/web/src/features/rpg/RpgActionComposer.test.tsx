import { MantineProvider } from '@mantine/core';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { FormEvent, ReactElement } from 'react';
import type { UseFormRegisterReturn } from 'react-hook-form';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { omnixApiClient } from '../../api/client';
import { omnixTheme } from '../../design/theme';
import { RpgActionComposer } from './RpgActionComposer';
import { previewSessionSummary, quickActions } from './rpgUiState';

function registration<TName extends 'sessionId' | 'command'>(name: TName): UseFormRegisterReturn<TName> {
  return {
    name,
    onBlur: vi.fn(),
    onChange: vi.fn(),
    ref: vi.fn(),
  };
}

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

describe('RpgActionComposer', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders replay-preserving turn controls and quick actions', () => {
    const onQuickAction = vi.fn();
    const onSubmit = vi.fn((event: FormEvent<HTMLFormElement>) => event.preventDefault());

    renderWithTheme(
      <RpgActionComposer
        commandRegistration={registration('command')}
        hasCommandError={false}
        isPending={false}
        onQuickAction={onQuickAction}
        onSubmit={onSubmit}
        quickActions={quickActions}
        sessionRegistration={registration('sessionId')}
        sessionSummaries={[previewSessionSummary]}
      />
    );

    expect(screen.getByRole('heading', { name: 'Turn request' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Queue RPG turn' })).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: 'Session' })).toHaveTextContent('Preview campaign — preview-session');
    expect(screen.getByRole('textbox', { name: 'Command' })).toHaveAttribute('aria-invalid', 'false');

    fireEvent.click(screen.getByRole('button', { name: 'Investigate' }));

    expect(onQuickAction).toHaveBeenCalledWith('Investigate the clawed tracks and torn Northern Watch banner.');
  });

  it('renders pending and invalid states for queued turn submission', () => {
    renderWithTheme(
      <RpgActionComposer
        commandRegistration={registration('command')}
        hasCommandError
        isPending
        onQuickAction={vi.fn()}
        onSubmit={vi.fn()}
        quickActions={quickActions}
        sessionRegistration={registration('sessionId')}
        sessionSummaries={[]}
      />
    );

    expect(screen.getByRole('button', { name: /Queueing/ })).toBeDisabled();
    expect(screen.getByRole('textbox', { name: 'Command' })).toHaveAttribute('aria-invalid', 'true');
  });

  it('sends selected capability identity when starting a new game', async () => {
    const createNewGame = vi.spyOn(omnixApiClient, 'createRpgNewGame').mockResolvedValue({
      ok: true,
      session_id: 'rpg_new_identity',
      status: 'ready',
      session: {},
      game: { session_id: 'rpg_new_identity' },
    });

    renderWithTheme(
      <RpgActionComposer
        commandRegistration={registration('command')}
        hasCommandError={false}
        isPending={false}
        onQuickAction={vi.fn()}
        onSubmit={vi.fn()}
        quickActions={quickActions}
        sessionRegistration={registration('sessionId')}
        sessionSummaries={[]}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: 'Campaign Menu' }));
    fireEvent.click(screen.getByRole('button', { name: /^New Game/ }));
    fireEvent.change(screen.getByRole('combobox', { name: 'Genre' }), { target: { value: 'cyberpunk' } });
    fireEvent.change(screen.getByRole('textbox', { name: 'Tone' }), { target: { value: 'street-level neon noir' } });
    fireEvent.change(screen.getByRole('textbox', { name: 'Background' }), { target: { value: 'corporate defector' } });
    fireEvent.change(screen.getByRole('combobox', { name: 'Primary capability' }), { target: { value: 'technical' } });
    fireEvent.change(screen.getByRole('combobox', { name: 'Power source' }), { target: { value: 'technology' } });

    const secondaryCapabilities = screen.getByRole('group', { name: 'Secondary capabilities' });
    fireEvent.click(within(secondaryCapabilities).getByLabelText('Survival'));
    fireEvent.click(within(secondaryCapabilities).getByLabelText('Combat'));
    fireEvent.click(within(secondaryCapabilities).getByLabelText('Knowledge'));
    fireEvent.click(within(secondaryCapabilities).getByLabelText('Recon'));
    fireEvent.click(screen.getByRole('button', { name: 'Start New Game' }));

    await waitFor(() => expect(createNewGame).toHaveBeenCalledTimes(1));
    expect(createNewGame).toHaveBeenCalledWith(
      expect.objectContaining({
        genre: 'cyberpunk',
        tone: 'street-level neon noir',
        background: 'corporate defector',
        player: expect.objectContaining({ background: 'corporate defector' }),
        primary_capability: 'technical',
        secondary_capabilities: ['knowledge', 'recon'],
        power_source: 'technology',
      })
    );
  });
});
