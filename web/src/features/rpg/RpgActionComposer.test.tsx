import { fireEvent, screen } from '@testing-library/react';
import type { FormEvent } from 'react';
import type { UseFormRegisterReturn } from 'react-hook-form';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { RpgActionComposer } from './RpgActionComposer';
import { rpgSessionClient } from './api/rpgSessionClient';
import { previewSessionSummary, quickActions } from './rpgUiState';
import { renderWithProviders } from '../../test/renderWithProviders';

function registration<TName extends 'sessionId' | 'command'>(name: TName): UseFormRegisterReturn<TName> {
  return {
    name,
    onBlur: vi.fn(),
    onChange: vi.fn(),
    ref: vi.fn(),
  };
}

function renderComposer(overrides: Partial<Parameters<typeof RpgActionComposer>[0]> = {}) {
  return renderWithProviders(
    <RpgActionComposer
      commandRegistration={registration('command')}
      hasCommandError={false}
      isPending={false}
      liveSessionId=""
      onQuickAction={vi.fn()}
      onSubmit={vi.fn((event: FormEvent<HTMLFormElement>) => event.preventDefault())}
      onTurnApplied={vi.fn()}
      quickActions={quickActions}
      selectedSessionId=""
      sessionRegistration={registration('sessionId')}
      sessionSummaries={[previewSessionSummary]}
      {...overrides}
    />
  );
}

describe('RpgActionComposer', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders the turn controls and quick actions', () => {
    const onQuickAction = vi.fn();
    renderComposer({ onQuickAction });

    expect(screen.getByRole('heading', { name: 'Your turn' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Submit RPG turn' })).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: 'Session' })).toHaveTextContent('Preview campaign — preview-session');
    expect(screen.getByRole('textbox', { name: 'Command' })).toHaveAttribute('aria-invalid', 'false');

    fireEvent.click(screen.getByRole('button', { name: 'Investigate' }));

    expect(onQuickAction).toHaveBeenCalledWith('Investigate the clawed tracks and torn Northern Watch banner.');
  });

  it('renders pending and invalid states for queued turn submission', () => {
    renderComposer({ hasCommandError: true, isPending: true, sessionSummaries: [] });

    expect(screen.getByRole('button', { name: /Sending/ })).toBeDisabled();
    expect(screen.getByRole('textbox', { name: 'Command' })).toHaveAttribute('aria-invalid', 'true');
  });

  it('undoes the last turn of the campaign being played, as a turn of its own', async () => {
    const rewind = vi.spyOn(rpgSessionClient, 'rewindRpgSession').mockResolvedValue({} as never);
    const onTurnApplied = vi.fn();
    renderComposer({ liveSessionId: 'session-live', onTurnApplied });

    fireEvent.click(screen.getByRole('button', { name: 'Undo last turn' }));

    await vi.waitFor(() => expect(onTurnApplied).toHaveBeenCalledTimes(1));
    expect(rewind).toHaveBeenCalledWith('session-live');
  });

  it('has nothing to undo without a campaign, or while a turn is on its way', () => {
    const { unmount } = renderComposer();
    expect(screen.getByRole('button', { name: 'Undo last turn' })).toBeDisabled();
    unmount();
    renderComposer({ liveSessionId: 'session-live', isPending: true });
    expect(screen.getByRole('button', { name: 'Undo last turn' })).toBeDisabled();
  });
});
