import { fireEvent, screen } from '@testing-library/react';
import type { FormEvent } from 'react';
import type { UseFormRegisterReturn } from 'react-hook-form';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { RpgActionComposer } from './RpgActionComposer';
import { rpgSessionClient } from './api/rpgSessionClient';
import { quickActions } from './rpgUiPreview';
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
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument(); // the Campaign Menu switches campaigns
    expect(screen.getByRole('textbox', { name: 'Command' })).toHaveAttribute('aria-invalid', 'false');

    fireEvent.click(screen.getByRole('button', { name: 'Investigate' }));

    expect(onQuickAction).toHaveBeenCalledWith(
      expect.objectContaining({ command: 'Investigate the clawed tracks and torn Northern Watch banner.' }),
    );
  });

  it('sends the turn on Enter and starts a new line on Shift+Enter', () => {
    const onSubmit = vi.fn((event: FormEvent<HTMLFormElement>) => event.preventDefault());
    renderComposer({ onSubmit });
    const command = screen.getByRole('textbox', { name: 'Command' });

    fireEvent.keyDown(command, { key: 'Enter', shiftKey: true });
    expect(onSubmit).not.toHaveBeenCalled();

    fireEvent.keyDown(command, { key: 'Enter' });
    expect(onSubmit).toHaveBeenCalledTimes(1);
  });

  it('asks the game master from beside the turn', () => {
    const onAskGameMaster = vi.fn();
    renderComposer({ onAskGameMaster });
    fireEvent.click(screen.getByRole('button', { name: 'Ask the game master' }));
    expect(onAskGameMaster).toHaveBeenCalledTimes(1);
  });

  it('renders pending and invalid states for queued turn submission', () => {
    renderComposer({ hasCommandError: true, isPending: true });

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
